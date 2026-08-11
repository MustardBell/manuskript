from dataclasses import replace

from manuskript.domain.assertion_dsl import encode_assertion_block
from manuskript.domain.canonical_project import (
    CanonicalProject,
    EntityRecord,
    OutlineDocument,
    StructuredMetadataField,
)
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTerm,
    StoryReference,
)
from manuskript.domain.structural_diff import (
    CanonicalProjectDiffer,
    StructuralChangeKind,
)


def _project():
    scene = OutlineDocument(
        "scene", "Opening", "scene",
        "Mara holds [[Objects/Key|the key]].\n\nSecond paragraph.",
        source_path="Manuscript/Opening.md",
    )
    entity = EntityRecord(
        OutlineDocument(
            "mara", "Mara", "entity", "Notes.",
            source_path="Characters/Mara.md",
        ),
        "character",
    )
    return CanonicalProject(format_version=2, outline=(scene,), entities=(entity,))


def test_structural_diff_reports_document_entity_reference_and_fact_changes():
    before = _project()
    assertion = Assertion(
        "owns-key", StoryReference("entity", "mara"), "possesses",
        AssertionTerm.referencing("entity", "key"),
    )
    previous_scene = before.outline[0]
    current_scene = replace(
        previous_scene,
        title="Aftermath",
        source_path="Part 1/Aftermath.md",
        text=(
            "Mara drops the key.\n\nChanged paragraph.\n\n"
            + encode_assertion_block(assertion)
        ),
        structured_metadata=(StructuredMetadataField("custom", True),),
    )
    renamed_entity = replace(
        before.entities[0],
        document=replace(before.entities[0].document, title="Mara Vale"),
    )
    after = replace(
        before, outline=(current_scene,), entities=(renamed_entity,)
    )

    report = CanonicalProjectDiffer().compare(before, after)
    kinds = {item.kind for item in report.changes}

    assert StructuralChangeKind.DOCUMENT_RENAMED in kinds
    assert StructuralChangeKind.DOCUMENT_MOVED in kinds
    assert StructuralChangeKind.DOCUMENT_METADATA in kinds
    assert StructuralChangeKind.PARAGRAPHS_CHANGED in kinds
    assert StructuralChangeKind.REFERENCE_DELETED in kinds
    assert StructuralChangeKind.ASSERTION_ADDED in kinds
    assert StructuralChangeKind.ENTITY_RENAMED in kinds
    assert sum(
        item.kind is StructuralChangeKind.DOCUMENT_RENAMED
        for item in report.changes
    ) == 1
    assert "assertion-added" in report.render_text()


def test_entity_addition_is_not_duplicated_as_a_document_addition():
    before = CanonicalProject(format_version=2)
    after = _project()

    report = CanonicalProjectDiffer().compare(before, after)
    entity_changes = tuple(
        item for item in report.changes if item.subject_id == "mara"
    )

    assert tuple(item.kind for item in entity_changes) == (
        StructuralChangeKind.ENTITY_ADDED,
    )


def test_structural_diff_reports_outline_reordering_separately_from_text():
    first = OutlineDocument("one", "One", "scene", "One")
    second = OutlineDocument("two", "Two", "scene", "Two")
    before = CanonicalProject(format_version=2, outline=(first, second))
    after = replace(before, outline=(second, first))

    report = CanonicalProjectDiffer().compare(before, after)

    assert tuple(item.kind for item in report.changes) == (
        StructuralChangeKind.DOCUMENT_MOVED,
        StructuralChangeKind.DOCUMENT_MOVED,
    )


def test_structural_diff_of_identical_projects_is_empty():
    project = _project()

    report = CanonicalProjectDiffer().compare(project, project)

    assert report.empty
    assert report.render_text() == "No structural changes."
