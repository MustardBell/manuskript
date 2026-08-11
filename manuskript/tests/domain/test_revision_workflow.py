import pytest

from manuskript.domain.canonical_project import (
    CanonicalProject,
    OutlineDocument,
)
from manuskript.domain.revision_workflow import (
    RevisionPassState,
    RevisionWorkflowStore,
    WORKFLOW_METADATA,
)


def _project(version=2):
    return CanonicalProject(
        format_version=version,
        outline=(OutlineDocument(
            "scene-1", "Opening", "scene", "Text.", raw_source="raw"
        ),),
    )


def test_revision_passes_are_independent_author_workflow_metadata():
    store = RevisionWorkflowStore()

    project = store.update(
        _project(), "scene-1", "structural", "in-progress"
    )
    project = store.update(
        project, "scene-1", "continuity", "complete"
    )

    workflow = store.workflow("scene-1")
    assert workflow.state("structural") is RevisionPassState.IN_PROGRESS
    assert workflow.state("continuity") is RevisionPassState.COMPLETE
    assert workflow.state("proof") is RevisionPassState.NOT_STARTED
    document = tuple(project.documents())[0]
    assert document.raw_source is None
    metadata = next(
        item for item in document.structured_metadata
        if item.name == WORKFLOW_METADATA
    )
    assert metadata.value["passes"]["continuity"] == "complete"


def test_returning_to_not_started_removes_empty_workflow_metadata():
    store = RevisionWorkflowStore()
    project = store.update(_project(), "scene-1", "draft", "complete")

    project = store.update(
        project, "scene-1", "draft", RevisionPassState.NOT_STARTED
    )

    assert tuple(project.documents())[0].structured_metadata == ()


def test_revision_workflow_refuses_unknown_passes_and_format_one_writes():
    store = RevisionWorkflowStore()

    with pytest.raises(KeyError):
        store.update(_project(), "scene-1", "invented", "complete")
    with pytest.raises(ValueError, match="Format 2"):
        store.update(_project(1), "scene-1", "draft", "complete")
