"""Format-independent revision-pass vocabulary and Format 2 metadata view."""

from dataclasses import dataclass, replace
from enum import Enum

from manuskript.domain.canonical_project import StructuredMetadataField


WORKFLOW_METADATA = "manuskript.revision_workflow"


class RevisionPassState(str, Enum):
    NOT_STARTED = "not-started"
    IN_PROGRESS = "in-progress"
    COMPLETE = "complete"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class RevisionPassDefinition:
    id: str
    label: str


DEFAULT_REVISION_PASSES = (
    RevisionPassDefinition("draft", "Draft"),
    RevisionPassDefinition("structural", "Structural"),
    RevisionPassDefinition("character", "Character"),
    RevisionPassDefinition("continuity", "Continuity"),
    RevisionPassDefinition("line", "Line"),
    RevisionPassDefinition("proof", "Proof"),
)


@dataclass(frozen=True)
class DocumentRevisionWorkflow:
    document_id: str
    states: tuple[tuple[str, RevisionPassState], ...] = ()

    def state(self, pass_id):
        return next(
            (
                state for identifier, state in self.states
                if identifier == str(pass_id)
            ),
            RevisionPassState.NOT_STARTED,
        )


class RevisionWorkflowStore:
    """Project metadata adapter; the canonical project remains authority."""

    def __init__(self, definitions=DEFAULT_REVISION_PASSES):
        self._definitions = tuple(definitions)
        self._workflows = {}

    @property
    def definitions(self):
        return self._definitions

    @property
    def workflows(self):
        return tuple(self._workflows.values())

    def workflow(self, document_id):
        return self._workflows.get(
            str(document_id), DocumentRevisionWorkflow(str(document_id))
        )

    def rebuild(self, project):
        workflows = {}
        if project is not None:
            for document in project.documents():
                value = _metadata_value(
                    document.structured_metadata, WORKFLOW_METADATA
                )
                workflows[document.id] = DocumentRevisionWorkflow(
                    document.id, _decode_states(value)
                )
        self._workflows = workflows
        return self.workflows

    def update(self, project, document_id, pass_id, state):
        if project is None or project.format_version != 2:
            raise ValueError(
                "Revision-pass metadata requires Project Format 2."
            )
        document_id = str(document_id)
        pass_id = str(pass_id)
        state = RevisionPassState(state)
        if pass_id not in {item.id for item in self._definitions}:
            raise KeyError(pass_id)
        found = False

        def update_document(document):
            nonlocal found
            children = tuple(update_document(child) for child in document.children)
            if document.id != document_id:
                return replace(document, children=children)
            found = True
            current = dict(_decode_states(_metadata_value(
                document.structured_metadata, WORKFLOW_METADATA
            )))
            if state is RevisionPassState.NOT_STARTED:
                current.pop(pass_id, None)
            else:
                current[pass_id] = state
            metadata = tuple(
                item for item in document.structured_metadata
                if item.name != WORKFLOW_METADATA
            )
            if current:
                metadata += (StructuredMetadataField(
                    WORKFLOW_METADATA,
                    {
                        "passes": {
                            identifier: value.value
                            for identifier, value in sorted(current.items())
                        }
                    },
                ),)
            return replace(
                document,
                structured_metadata=metadata,
                children=children,
                raw_source=None,
            )

        outline = tuple(update_document(item) for item in project.outline)
        entities = tuple(
            replace(entity, document=update_document(entity.document))
            for entity in project.entities
        )
        if not found:
            raise KeyError(document_id)
        updated = replace(project, outline=outline, entities=entities)
        self.rebuild(updated)
        return updated


def _metadata_value(metadata, name):
    return next(
        (item.value for item in reversed(metadata) if item.name == name),
        None,
    )


def _decode_states(value):
    if not isinstance(value, dict):
        return ()
    passes = value.get("passes", {})
    if not isinstance(passes, dict):
        return ()
    states = []
    for identifier, raw_state in passes.items():
        try:
            state = RevisionPassState(str(raw_state))
        except ValueError:
            continue
        if state is not RevisionPassState.NOT_STARTED:
            states.append((str(identifier), state))
    return tuple(sorted(states))
