import logging
from dataclasses import replace

from manuskript import loadSave
from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.load_save.legacy_archive import Version0ProjectArchive
from manuskript.load_save.format_detection import (
    ProjectFormatDetector,
)
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.project_files import ProjectFileReadResult
from manuskript.load_save.version_1_codec import (
    REQUIRED_FILES,
    Version1ProjectCodec,
)
from manuskript.load_save.version_0_codec import Version0ProjectCodec
from manuskript.load_save.version_2_codec import Version2ProjectCodec
from manuskript.services.legacy_project_adapter import (
    LegacyApplicationModelAdapter,
)
from manuskript.services.legacy_entity_adapter import LegacyEntityAdapter
from manuskript.domain.entity_catalog import (
    EntityCatalog,
    first_party_story_entity_schemas,
)
from manuskript.domain.assertion_store import (
    AssertionDocument,
    AssertionStore,
)
from manuskript.domain.morphology import MorphologyIndex
from manuskript.domain.project_features import compatibility_strategy
from manuskript.domain.reference_index import (
    ReferenceDocument,
    ReferenceIndex,
)
from manuskript.domain.story_query import StoryQueryEngine
from manuskript.domain.rule_store import RuleDocument, RuleStore
from manuskript.domain.story_rules import StoryRuleEngine
from manuskript.domain.revision_workflow import RevisionWorkflowStore
from manuskript.domain.temporal_story import (
    ChronologyIndex,
    TemporalStoryIndex,
)
from manuskript.linguistics import installed_morphology_schemas


LOGGER = logging.getLogger(__name__)


class ProjectStorage:
    """Persistence boundary and exception shield for the project lifecycle."""

    def __init__(
        self,
        file_cache=None,
        file_access=None,
        legacy_file_access=None,
        format_detector=None,
        version_1_codec=None,
        version_0_codec=None,
        version_2_codec=None,
        application_model_adapter=None,
        entity_catalog=None,
        legacy_entity_adapter=None,
        morphology_schemas=None,
        assertion_store=None,
        chronology_index=None,
        rule_store=None,
        revision_workflow=None,
    ):
        self._file_cache = (
            file_cache if file_cache is not None else {}
        )
        self._file_access = (
            file_access
            if file_access is not None
            else Version1ProjectFiles()
        )
        self._legacy_file_access = (
            legacy_file_access
            if legacy_file_access is not None
            else Version0ProjectArchive()
        )
        self._format_detector = format_detector or ProjectFormatDetector()
        self._version_1_codec = version_1_codec or Version1ProjectCodec()
        self._version_0_codec = version_0_codec or Version0ProjectCodec()
        self._version_2_codec = version_2_codec or Version2ProjectCodec()
        self._application_model_adapter = (
            application_model_adapter or LegacyApplicationModelAdapter()
        )
        self._morphology_schemas = (
            morphology_schemas or installed_morphology_schemas()
        )
        self._morphology_index = MorphologyIndex(
            self._morphology_schemas
        )
        self._entity_catalog = entity_catalog or EntityCatalog(
            first_party_story_entity_schemas(),
            morphology_index=self._morphology_index,
        )
        self._legacy_entity_adapter = (
            legacy_entity_adapter or LegacyEntityAdapter()
        )
        self._canonical_project = None
        self._reference_index = ReferenceIndex()
        self._assertion_store = assertion_store or AssertionStore()
        self._chronology_index = chronology_index or ChronologyIndex()
        self._temporal_story = TemporalStoryIndex(
            self._assertion_store, self._chronology_index
        )
        self._rule_store = rule_store or RuleStore()
        self._story_rules = StoryRuleEngine(
            self._assertion_store,
            self._chronology_index,
            self._temporal_story,
            self._rule_store,
        )
        self._revision_workflow = (
            revision_workflow or RevisionWorkflowStore()
        )
        self._story_query = StoryQueryEngine(
            self._entity_catalog,
            self._reference_index,
            self._assertion_store,
        )

    @property
    def canonical_project(self):
        return self._canonical_project

    @property
    def persistence_strategy(self):
        if self._canonical_project is None:
            return compatibility_strategy(-1)
        return compatibility_strategy(
            self._canonical_project.format_version
        )

    def capture_current(self, context):
        """Project the live application models without writing or adopting.

        Read-only tools such as structural diff need the state on screen,
        including edits made since the last save. Returning a detached
        canonical value keeps them from treating the last disk snapshot as
        current or mutating persistence as a side effect of inspection.
        """

        if self._canonical_project is None:
            raise ValueError("No canonical project is open.")
        project = self._application_model_adapter.capture(
            context, self._canonical_project
        )
        if project.format_version == 2:
            project = replace(
                project,
                entities=self._entity_catalog.native_entities,
                summary=(),
                characters=(),
                world=(),
                plots=(),
            )
        return project

    @property
    def reference_index(self):
        return self._reference_index

    @property
    def entity_catalog(self):
        return self._entity_catalog

    @property
    def morphology_schemas(self):
        return self._morphology_schemas

    @property
    def assertion_store(self):
        return self._assertion_store

    @property
    def story_query(self):
        return self._story_query

    @property
    def chronology(self):
        return self._chronology_index

    @property
    def temporal_story(self):
        return self._temporal_story

    @property
    def rule_store(self):
        return self._rule_store

    @property
    def story_rules(self):
        return self._story_rules

    @property
    def revision_workflow(self):
        return self._revision_workflow

    def update_revision_pass(self, document_id, pass_id, state):
        self._canonical_project = self._revision_workflow.update(
            self._canonical_project, document_id, pass_id, state
        )
        return self._revision_workflow.workflow(document_id)

    def register_morphology_schema(self, schema):
        self._morphology_schemas.register(schema)
        self._entity_catalog.refresh_derived_surfaces()
        entity_by_id = {
            entity.id: entity for entity in self._entity_catalog.entities
        }
        self._reference_index.rebuild(tuple(
            replace(
                document,
                aliases=self._entity_reference_surfaces(
                    entity_by_id[document.id]
                ),
            )
            if document.id in entity_by_id else document
            for document in self._reference_index.documents
        ))
        self._rebuild_assertions()

    def create_entity(self, entity_type, title, aliases=()):
        entity = self._entity_catalog.create(entity_type, title, aliases)
        self._reference_index.update(ReferenceDocument(
            id=entity.id,
            path=entity.document.source_path,
            title=entity.title,
            text=entity.document.text,
            aliases=self._entity_reference_surfaces(entity),
        ))
        self._rebuild_assertions()
        return entity

    def update_entity(self, entity_id, **changes):
        entity = self._entity_catalog.update(entity_id, **changes)
        self._reference_index.update(ReferenceDocument(
            id=entity.id,
            path=entity.document.source_path,
            title=entity.title,
            text=entity.document.text,
            aliases=self._entity_reference_surfaces(entity),
        ))
        self._rebuild_assertions()
        return entity

    def delete_entity(self, entity_id):
        entity = self._entity_catalog.delete(entity_id)
        self._reference_index.remove(entity.document.id)
        self._rebuild_assertions()
        return entity

    def update_document_references(self, item):
        """Incrementally re-index one live outline item after an edit."""

        if self._canonical_project is None or item is None:
            return
        self._reference_index.update(self._reference_document_from_item(item))
        self._rebuild_assertions()

    def rebuild_document_references(self, root_item):
        """Re-index live outline structure after inserts, moves, or removals."""

        if self._canonical_project is None or root_item is None:
            return
        documents = []

        def collect(parent):
            for child in parent.children():
                documents.append(self._reference_document_from_item(child))
                collect(child)

        collect(root_item)
        documents.extend(
            ReferenceDocument(
                id=entity.id,
                path=entity.document.source_path,
                title=entity.title,
                text=entity.document.text,
                aliases=self._entity_reference_surfaces(entity),
            )
            for entity in self._entity_catalog.entities
        )
        self._reference_index.rebuild(documents)
        self._rebuild_assertions()

    @staticmethod
    def _reference_document_from_item(item):
        from manuskript.enums import Outline
        fallback_path = item.path("/") if item.parent() is not None else item.title()
        return ReferenceDocument(
            id=str(item.ID() or ""),
            path=str(getattr(item, "_lastPath", "") or fallback_path),
            title=str(item.title() or ""),
            text=str(item.data(Outline.text) or ""),
        )

    def load(self, context):
        try:
            detected = self._format_detector.detect(context.project_file)
            if detected.version == 1:
                return self._load_version_1(
                    context,
                    zipped=detected.zipped,
                    file_access=self._file_access,
                )
            if detected.version == 2:
                return self._load_version_2(
                    context,
                    zipped=detected.zipped,
                    file_access=self._file_access,
                )
            if detected.version == 0:
                project = self._version_0_codec.decode(
                    self._legacy_file_access.read(context.project_file),
                    zipped=True,
                )
                self._adopt_canonical_project(project)
            return loadSave.loadProject(
                context,
                cache=self._file_cache,
                file_access=self._file_access,
                legacy_file_access=self._legacy_file_access,
            )
        except Exception as error:
            message = self._failure_message("load", context, error)
            LOGGER.exception(message)
            return ProjectLoadResult(fatal_errors=(message,))

    def save(self, context, version=None):
        try:
            selected_version = (
                self._canonical_project.format_version
                if version is None
                and self._canonical_project is not None
                else 1 if version is None else version
            )
            if selected_version == 1:
                return self._save_version_1(context)
            if selected_version == 2:
                return self._save_version_2(context)
            return loadSave.saveProject(
                context,
                version=version,
                cache=self._file_cache,
                file_access=self._file_access,
                legacy_file_access=self._legacy_file_access,
            )
        except Exception as error:
            LOGGER.exception(
                self._failure_message("save", context, error)
            )
            return ProjectSaveResult(
                failed_files=(context.project_file,)
            )

    def load_snapshot(self, context, snapshot):
        """Hydrate models from immutable in-memory project files."""
        try:
            return self._load_version_1(
                context,
                zipped=snapshot.zipped,
                file_access=InMemoryProjectFiles(snapshot.files),
            )
        except Exception as error:
            message = self._failure_message(
                "load revision snapshot",
                context,
                error,
            )
            LOGGER.exception(message)
            return ProjectLoadResult(fatal_errors=(message,))

    def clear_cache(self):
        self._file_cache.clear()
        self._canonical_project = None
        self._reference_index.rebuild(())
        self._assertion_store.rebuild(())
        self._chronology_index.rebuild(())
        self._rule_store.rebuild(())
        self._revision_workflow.rebuild(None)
        self._entity_catalog.replace((), writable=False)

    def _load_version_1(self, context, *, zipped, file_access):
        read_result = file_access.read(
            context.project_file,
            zipped=bool(zipped),
        )
        project = self._version_1_codec.decode(
            read_result.files,
            zipped=bool(zipped),
        )
        self._application_model_adapter.hydrate(project, context)
        self._adopt_canonical_project(project)
        if not zipped:
            self._file_cache.clear()
            self._file_cache.update(read_result.files)
        missing = tuple(
            path for path in REQUIRED_FILES
            if path not in read_result.files
        )
        diagnostics = tuple(
            "{}: {}".format(issue.source.path, issue.message)
            for issue in project.issues
            if issue.source.path not in missing
        )
        return ProjectLoadResult(
            missing_files=missing,
            unreadable_files=read_result.unreadable_files,
            diagnostics=diagnostics,
        )

    def _save_version_1(self, context):
        before = self._canonical_project or self._version_1_codec.decode(
            {}, zipped=bool(context.settings.saveToZip)
        )
        project = self._application_model_adapter.capture(context, before)
        encoded = self._version_1_codec.encode(project)
        result = self._file_access.write(
            context.project_file,
            zipped=project.zipped,
            files=encoded.files,
            moves=self._application_model_adapter.moves(before, project),
            cache=self._file_cache,
            marker_version=1,
        )
        if result.succeeded:
            project = self._version_1_codec.decode(
                dict(encoded.files), zipped=project.zipped
            )
            self._adopt_canonical_project(project)
        return result

    def _load_version_2(self, context, *, zipped, file_access):
        read_result = file_access.read(
            context.project_file, zipped=bool(zipped)
        )
        project = self._version_2_codec.decode(
            read_result.files, zipped=bool(zipped)
        )
        fatal = tuple(
            "{}: {}".format(issue.source.path, issue.message)
            for issue in self._version_2_codec.validate(project)
            if issue.severity == "error"
        )
        if fatal:
            return ProjectLoadResult(
                unreadable_files=read_result.unreadable_files,
                fatal_errors=fatal,
            )
        self._application_model_adapter.hydrate(project, context)
        self._adopt_canonical_project(project)
        if not zipped:
            self._file_cache.clear()
            self._file_cache.update(read_result.files)
        return ProjectLoadResult(
            unreadable_files=read_result.unreadable_files,
            diagnostics=tuple(
                "{}: {}".format(issue.source.path, issue.message)
                for issue in project.issues
            ),
        )

    def _save_version_2(self, context):
        before = self._canonical_project
        if before is None or before.format_version != 2:
            before = self._version_2_codec.decode(
                {}, zipped=bool(context.settings.saveToZip)
            )
        project = self._application_model_adapter.capture(context, before)
        project = replace(
            project,
            entities=self._entity_catalog.native_entities,
            # Format 2 has one story vocabulary.  The legacy application
            # models are still hydrated for old outline metadata and codec
            # compatibility, but they are not a second persisted source of
            # summaries, characters, plots, or world records.
            summary=(),
            characters=(),
            world=(),
            plots=(),
        )
        issues = tuple(
            issue for issue in self._version_2_codec.validate(project)
            if issue.severity == "error"
        )
        if issues:
            return ProjectSaveResult(failed_files=tuple(
                issue.source.path or context.project_file for issue in issues
            ))
        encoded = self._version_2_codec.encode(project)
        result = self._file_access.write(
            context.project_file,
            zipped=project.zipped,
            files=encoded.files,
            moves=self._application_model_adapter.moves(before, project),
            cache=self._file_cache,
            marker_version=2,
        )
        if result.succeeded:
            project = self._version_2_codec.decode(
                dict(encoded.files), zipped=project.zipped
            )
            self._adopt_canonical_project(project)
        return result

    def _adopt_canonical_project(self, project):
        strategy = compatibility_strategy(project.format_version)
        self._reference_index.set_enabled(
            strategy.supports("references.read")
        )
        self._morphology_index.set_enabled(
            strategy.supports("morphology.entities")
        )
        projected = self._legacy_entity_adapter.project(project)
        native_ids = {entity.id for entity in project.entities}
        missing_projected = tuple(
            entity for entity in projected if entity.id not in native_ids
        )
        if project.format_version == 2:
            # Format 2 has not shipped and has no compatibility population.
            # Its entity documents are authoritative; do not carry migration
            # behavior for intermediate development encodings into the
            # architecture being built.
            native_entities = project.entities
            legacy_entities = ()
        else:
            native_entities = project.entities
            legacy_entities = missing_projected

        self._canonical_project = project
        self._revision_workflow.rebuild(project)
        self._entity_catalog.replace(
            native_entities,
            legacy_entities,
            writable=project.format_version == 2,
        )
        entity_aliases = {
            entity.id: self._entity_reference_surfaces(entity)
            for entity in self._entity_catalog.entities
        }
        documents = list(project.documents())
        document_ids = {document.id for document in documents}
        documents.extend(
            entity.document
            for entity in self._entity_catalog.entities
            if entity.id not in document_ids
        )
        self._reference_index.rebuild(tuple(
            ReferenceDocument(
                id=document.id,
                path=document.source_path,
                title=document.title,
                text=document.text,
                aliases=entity_aliases.get(document.id, ()),
            )
            for document in documents
        ))
        self._rebuild_assertions()

    def _entity_reference_surfaces(self, entity):
        return tuple(
            value for value in self._entity_catalog.surface_forms(entity.id)
            if value.casefold() != entity.title.casefold()
        )

    def _rebuild_assertions(self):
        if not self.persistence_strategy.supports("assertions.read"):
            # A legacy document may contain the same fenced text by chance.
            # Preserving those bytes is not permission to execute or project
            # them as Format 2 story data.
            self._assertion_store.rebuild(())
            self._rule_store.rebuild(())
            self._chronology_index.rebuild(())
            return
        entity_ids = tuple(
            entity.id for entity in self._entity_catalog.entities
        )
        entity_id_set = set(entity_ids)
        self._assertion_store.rebuild(
            (
                AssertionDocument(
                    document.id, document.path, document.text
                )
                for document in self._reference_index.documents
            ),
            entity_ids=entity_ids,
        )
        self._rule_store.rebuild(
            RuleDocument(document.id, document.path, document.text)
            for document in self._reference_index.documents
        )
        self._chronology_index.rebuild(
            self._assertion_store.assertions,
            narrative_ids=(
                document.id
                for document in self._reference_index.documents
                if document.id not in entity_id_set
            ),
        )

    @staticmethod
    def _failure_message(operation, context, error):
        return "Cannot {} project {}: {}: {}".format(
            operation,
            context.project_file,
            type(error).__name__,
            error,
        )


class InMemoryProjectFiles:
    """Version-1 file reader backed by an already materialized snapshot."""

    def __init__(self, files):
        self._files = dict(files)

    def read(self, _project_file, *, zipped):
        return ProjectFileReadResult(files=dict(self._files))
