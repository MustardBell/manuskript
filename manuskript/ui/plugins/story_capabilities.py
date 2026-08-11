"""Capability-gated plugin façades over the explicit story domain."""

import uuid
from dataclasses import replace

from manuskript.enums import Outline
from manuskript.domain.assertion_dsl import (
    assertions_from_source,
    encode_assertion_block,
)
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionProvenance,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
)
from manuskript.plugins.api import (
    AssertionDiagnosticSnapshot,
    AssertionSnapshot,
    AssertionTermValue,
    EntitySnapshot,
    MorphologyProviderSnapshot,
    ReferenceOccurrenceSnapshot,
    ReferenceSuggestionSnapshot,
    StoryReferenceValue,
    WorkspaceDocument,
)
from manuskript.plugins.capabilities import (
    CAPABILITY_ASSERTIONS_READ,
    CAPABILITY_ASSERTIONS_WRITE,
    CAPABILITY_ENTITIES_READ,
    CAPABILITY_ENTITIES_WRITE,
    CAPABILITY_MORPHOLOGY_REGISTRY,
    CAPABILITY_QUERY_EXECUTE,
    CAPABILITY_REFERENCES_READ,
    CAPABILITY_REFERENCES_WRITE,
)
from manuskript.plugins.errors import PluginScopeError


_PERSISTED_CAPABILITIES = frozenset((
    CAPABILITY_ENTITIES_READ,
    CAPABILITY_ENTITIES_WRITE,
    CAPABILITY_REFERENCES_READ,
    CAPABILITY_REFERENCES_WRITE,
    CAPABILITY_ASSERTIONS_READ,
    CAPABILITY_ASSERTIONS_WRITE,
))


def _flush_pending(manager):
    buffers = getattr(manager, "document_buffers", None)
    if buffers is not None:
        buffers.flush()


class ProjectSourceGateway:
    """Narrow source command port for project panels and story services."""

    def __init__(self, manager):
        self._manager = manager

    def document(self, document_id):
        models = getattr(self._manager, "models", None)
        outline = getattr(models, "outline", None)
        item = (
            outline.getItemByID(str(document_id))
            if outline is not None else None
        )
        if item is None or not item.isText():
            return None
        parent = item.parent()
        return WorkspaceDocument(
            id=str(item.ID()),
            title=str(item.title()),
            kind=str(item.type()),
            text=str(item.text() or ""),
            compile=bool(item.compile()),
            parent_id=(
                str(parent.ID())
                if parent is not None and parent is not outline.rootItem
                else None
            ),
        )

    def set_text(self, document_id, text):
        models = getattr(self._manager, "models", None)
        outline = getattr(models, "outline", None)
        item = (
            outline.getItemByID(str(document_id))
            if outline is not None else None
        )
        if item is None or not item.isText():
            raise KeyError(document_id)
        index = outline.getIndexByID(
            str(document_id), column=Outline.text
        )
        if not index.isValid():
            raise KeyError(document_id)
        if str(item.text() or "") == str(text):
            return False
        return bool(outline.setData(index, str(text)))


def build_story_capability(
        runtime, manager, plugin_id, name, source_gateway=None):
    """Resolve one declared project service without exposing core state."""

    if not runtime.declares(plugin_id, name):
        raise PluginScopeError(
            "Plugin {} did not declare capability {!r} in its manifest."
            .format(plugin_id, name)
        )
    if manager is None or not manager.session.is_open:
        raise PluginScopeError("No project is open.")
    if name in _PERSISTED_CAPABILITIES:
        support = manager.storage.persistence_strategy.support(name)
        writable = name.endswith(".write")
        available = support.writable if writable else support.readable
        if not available:
            raise PluginScopeError(
                support.reason
                or "The project cannot provide {}.".format(name)
            )
    source = (
        source_gateway
        if source_gateway is not None
        else ProjectSourceGateway(manager)
    )
    builders = {
        CAPABILITY_ENTITIES_READ: lambda: EntityReadCapability(manager),
        CAPABILITY_ENTITIES_WRITE: lambda: EntityWriteCapability(manager),
        CAPABILITY_REFERENCES_READ: lambda: ReferenceReadCapability(manager),
        CAPABILITY_REFERENCES_WRITE: lambda: ReferenceWriteCapability(
            manager, source
        ),
        CAPABILITY_ASSERTIONS_READ: lambda: AssertionReadCapability(manager),
        CAPABILITY_ASSERTIONS_WRITE: lambda: AssertionWriteCapability(
            manager, source
        ),
        CAPABILITY_QUERY_EXECUTE: lambda: QueryExecuteCapability(manager),
        CAPABILITY_MORPHOLOGY_REGISTRY: lambda: (
            MorphologyRegistryCapability(manager, plugin_id)
        ),
    }
    builder = builders.get(name)
    if builder is None:
        raise PluginScopeError(
            "Capability {!r} is not a project story service.".format(name)
        )
    return builder()


def _entity_snapshot(entity):
    return EntitySnapshot(
        entity.id,
        entity.type,
        entity.title,
        entity.document.source_path,
        entity.aliases,
        {item.name: item.value for item in entity.metadata},
    )


def _reference_value(reference):
    return StoryReferenceValue(reference.kind, reference.id)


def _assertion_snapshot(assertion):
    span = assertion.provenance.source_span
    return AssertionSnapshot(
        assertion.id,
        _reference_value(assertion.subject),
        assertion.predicate,
        AssertionTermValue(
            reference=(
                _reference_value(assertion.object.reference)
                if assertion.object.reference is not None
                else None
            ),
            value=assertion.object.value,
            is_reference=assertion.object.reference is not None,
        ),
        {item.name: item.value for item in assertion.qualifiers},
        assertion.provenance.document_id,
        span.start if span is not None else 0,
        span.end if span is not None else 0,
        assertion.provenance.anchor,
        assertion.provenance.note,
        assertion.canon_state.value,
    )


def _occurrence_snapshot(occurrence):
    return ReferenceOccurrenceSnapshot(
        occurrence.source_document_id,
        occurrence.source_path,
        occurrence.source_span.start,
        occurrence.source_span.end,
        occurrence.raw_target,
        occurrence.display_text,
        occurrence.resolution.value,
        occurrence.resolved_target_id,
        occurrence.resolved_target_path,
    )


def _suggestion_snapshot(suggestion):
    return ReferenceSuggestionSnapshot(
        suggestion.document_id,
        suggestion.target,
        suggestion.title,
        suggestion.path,
    )


def _diagnostic_snapshot(issue):
    return AssertionDiagnosticSnapshot(
        issue.document_id,
        issue.path,
        issue.message,
        issue.severity,
        issue.source_span.start,
        issue.source_span.end,
    )


class EntityReadCapability:
    def __init__(self, manager):
        self._catalog = manager.storage.entity_catalog

    def entities(self):
        return tuple(_entity_snapshot(item) for item in self._catalog.entities)

    def find(self, entity_id):
        entity = self._catalog.find(str(entity_id))
        return _entity_snapshot(entity) if entity is not None else None

    def exact_matches(self, surface):
        return tuple(
            _entity_snapshot(item)
            for item in self._catalog.exact_matches(str(surface))
        )


class EntityWriteCapability(EntityReadCapability):
    def __init__(self, manager):
        super().__init__(manager)
        self._manager = manager

    def create(self, entity_type, title, aliases=()):
        return _entity_snapshot(self._manager.createEntity(
            str(entity_type), str(title), tuple(str(item) for item in aliases)
        ))

    def update(self, entity_id, **changes):
        allowed = {"title", "entity_type", "aliases", "text"}
        unknown = set(changes).difference(allowed)
        if unknown:
            raise TypeError(
                "Unsupported entity changes: {}".format(
                    ", ".join(sorted(unknown))
                )
            )
        changes = dict(changes)
        if "aliases" in changes:
            changes["aliases"] = tuple(
                str(item) for item in changes["aliases"]
            )
        for name in ("title", "entity_type", "text"):
            if name in changes:
                changes[name] = str(changes[name])
        return _entity_snapshot(
            self._manager.updateEntity(str(entity_id), **changes)
        )


class ReferenceReadCapability:
    def __init__(self, manager):
        self._index = manager.storage.reference_index

    def occurrences(self):
        return tuple(
            _occurrence_snapshot(item) for item in self._index.references
        )

    def backlinks(self, target_id):
        return tuple(
            _occurrence_snapshot(item)
            for item in self._index.backlinks(str(target_id))
        )

    def complete(self, prefix):
        return tuple(
            _suggestion_snapshot(item)
            for item in self._index.complete(str(prefix))
        )


class ReferenceWriteCapability(ReferenceReadCapability):
    def __init__(self, manager, outline):
        super().__init__(manager)
        self._manager = manager
        self._outline = outline

    def insert(self, document_id, start, end, target, display=None):
        _flush_pending(self._manager)
        document = self._outline.document(str(document_id))
        if document is None:
            raise KeyError(document_id)
        start, end = int(start), int(end)
        if start < 0 or end < start or end > len(document.text):
            raise ValueError("Reference insertion span is outside the source.")
        target = str(target).strip()
        if not target or any(
            value in target for value in ("[", "]", "|", "\n")
        ):
            raise ValueError("Reference target is invalid.")
        display = None if display is None else str(display)
        if display is not None and any(
            value in display for value in ("]", "\n")
        ):
            raise ValueError("Reference display text is invalid.")
        link = "[[{}]]".format(target) if display is None else (
            "[[{}|{}]]".format(target, display)
        )
        changed = document.text[:start] + link + document.text[end:]
        self._outline.set_text(document.id, changed)
        return changed


class AssertionReadCapability:
    def __init__(self, manager):
        self._store = manager.storage.assertion_store

    def assertions(self):
        return tuple(
            _assertion_snapshot(item) for item in self._store.assertions
        )

    def find(self, assertion_id):
        item = self._store.find(str(assertion_id))
        return _assertion_snapshot(item) if item is not None else None

    def relationships(self, predicate=""):
        return tuple(
            _assertion_snapshot(item)
            for item in self._store.relationships(str(predicate))
        )

    def diagnostics(self):
        return tuple(
            _diagnostic_snapshot(item) for item in self._store.issues
        )


class AssertionWriteCapability(AssertionReadCapability):
    def __init__(self, manager, outline, id_factory=None):
        super().__init__(manager)
        self._manager = manager
        self._outline = outline
        self._idFactory = id_factory or (lambda: str(uuid.uuid4()))

    def append_relationship(
        self,
        document_id,
        subject,
        predicate,
        object_reference,
        *,
        qualifiers=None,
        canon_state="canon",
        anchor="",
        note="",
    ):
        return self._append(
            document_id,
            self._assertion(
                subject,
                predicate,
                AssertionTerm.referencing(
                    object_reference.kind, object_reference.id
                ),
                qualifiers,
                canon_state,
                anchor,
                note,
            ),
        )

    def append_value(
        self,
        document_id,
        subject,
        predicate,
        value,
        *,
        qualifiers=None,
        canon_state="canon",
        anchor="",
        note="",
    ):
        return self._append(
            document_id,
            self._assertion(
                subject,
                predicate,
                AssertionTerm.scalar(value),
                qualifiers,
                canon_state,
                anchor,
                note,
            ),
        )

    def remove(self, assertion_id):
        _flush_pending(self._manager)
        existing = self._store.find(str(assertion_id))
        if existing is None:
            return False
        document = self._outline.document(existing.provenance.document_id)
        if document is None:
            raise KeyError(existing.provenance.document_id)
        assertions, _diagnostics = assertions_from_source(document.text)
        current = next(
            (item for item in assertions if item.id == existing.id), None
        )
        if current is None or current.provenance.source_span is None:
            raise ValueError("Assertion source changed before it was removed.")
        span = current.provenance.source_span
        changed = document.text[:span.start] + document.text[span.end:]
        self._outline.set_text(document.id, changed)
        return True

    def set_canon_state(self, assertion_id, canon_state):
        _flush_pending(self._manager)
        existing = self._store.find(str(assertion_id))
        if existing is None:
            raise KeyError(assertion_id)
        document = self._outline.document(existing.provenance.document_id)
        assertions, _diagnostics = assertions_from_source(document.text)
        current = next(item for item in assertions if item.id == existing.id)
        updated = replace(
            current,
            canon_state=CanonState(canon_state),
            provenance=replace(
                current.provenance,
                document_id=existing.provenance.document_id,
            ),
        )
        span = current.provenance.source_span
        changed = (
            document.text[:span.start]
            + encode_assertion_block(updated)
            + document.text[span.end:]
        )
        self._outline.set_text(document.id, changed)
        indexed = self._store.find(updated.id)
        return _assertion_snapshot(indexed or updated)

    def _append(self, document_id, assertion):
        _flush_pending(self._manager)
        document = self._outline.document(str(document_id))
        if document is None:
            raise KeyError(document_id)
        assertion = replace(
            assertion,
            provenance=replace(
                assertion.provenance, document_id=document.id
            ),
        )
        separator = "" if not document.text else (
            "" if document.text.endswith("\n\n")
            else "\n" if document.text.endswith("\n") else "\n\n"
        )
        self._outline.set_text(
            document.id,
            document.text + separator + encode_assertion_block(assertion),
        )
        indexed = self._store.find(assertion.id)
        return _assertion_snapshot(indexed or assertion)

    def _assertion(
        self, subject, predicate, term, qualifiers, canon_state, anchor, note
    ):
        return Assertion(
            str(self._idFactory()),
            StoryReference(str(subject.kind), str(subject.id)),
            str(predicate),
            term,
            tuple(
                AssertionQualifier(str(name), value)
                for name, value in (qualifiers or {}).items()
            ),
            AssertionProvenance(anchor=str(anchor), note=str(note)),
            CanonState(canon_state),
        )


class QueryExecuteCapability:
    def __init__(self, manager):
        self._query = manager.storage.story_query

    def execute(self, expression):
        return self._query.execute(expression)


class MorphologyRegistryCapability:
    def __init__(self, manager, plugin_id):
        self._manager = manager
        self._pluginId = plugin_id

    def providers(self):
        return tuple(
            MorphologyProviderSnapshot(
                provider.id, provider.label, provider.language
            )
            for provider in self._manager.storage.morphology_providers.providers
        )

    def register(self, provider):
        if not str(provider.id).startswith(self._pluginId + "."):
            raise ValueError(
                "Plugin morphology provider IDs must start with {}.".format(
                    self._pluginId + "."
                )
            )
        self._manager.storage.register_morphology_provider(provider)
        return MorphologyProviderSnapshot(
            provider.id, provider.label, provider.language
        )
