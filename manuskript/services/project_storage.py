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
from manuskript.domain.morphology import MorphologyIndex
from manuskript.domain.project_features import compatibility_strategy
from manuskript.domain.reference_index import (
    ReferenceDocument,
    ReferenceIndex,
)
from manuskript.linguistics import first_party_morphology_providers


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
        morphology_providers=None,
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
        self._morphology_providers = (
            morphology_providers or first_party_morphology_providers()
        )
        self._morphology_index = MorphologyIndex(
            self._morphology_providers
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

    @property
    def reference_index(self):
        return self._reference_index

    @property
    def entity_catalog(self):
        return self._entity_catalog

    @property
    def morphology_providers(self):
        return self._morphology_providers

    def create_entity(self, entity_type, title, aliases=()):
        entity = self._entity_catalog.create(entity_type, title, aliases)
        self._reference_index.update(ReferenceDocument(
            id=entity.id,
            path=entity.document.source_path,
            title=entity.title,
            text=entity.document.text,
            aliases=self._entity_reference_surfaces(entity),
        ))
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
        return entity

    def update_document_references(self, item):
        """Incrementally re-index one live outline item after an edit."""

        if self._canonical_project is None or item is None:
            return
        self._reference_index.update(
            self._reference_document_from_item(item)
        )

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
            for entity in self._entity_catalog.native_entities
        )
        self._reference_index.rebuild(documents)

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
        self._canonical_project = project
        legacy_entities = (
            self._legacy_entity_adapter.project(project)
            if project.format_version in (0, 1)
            else ()
        )
        self._entity_catalog.replace(
            project.entities,
            legacy_entities,
            writable=project.format_version == 2,
        )
        entity_aliases = {
            entity.id: self._entity_reference_surfaces(entity)
            for entity in project.entities
        }
        self._reference_index.rebuild(tuple(
            ReferenceDocument(
                id=document.id,
                path=document.source_path,
                title=document.title,
                text=document.text,
                aliases=entity_aliases.get(document.id, ()),
            )
            for document in project.documents()
        ))

    def _entity_reference_surfaces(self, entity):
        return tuple(
            value for value in self._entity_catalog.surface_forms(entity.id)
            if value.casefold() != entity.title.casefold()
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
