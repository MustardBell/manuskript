from manuskript.domain.entity_catalog import EntityReferenceChoice
from manuskript.domain.story_assertions import (
    AssertionTermKind,
    CanonState,
    StoryReference,
)
from manuskript.ui.assertion_editor import AssertionEditorDialog


def _dialog():
    choices = (EntityReferenceChoice(
        "mara", "character", "Mara Vale", "Characters/Mara Vale"
    ),)
    return AssertionEditorDialog(
        StoryReference("document", "scene-18"),
        choices,
        id_factory=lambda: "assertion-1",
    )


def test_assertion_dialog_builds_an_explicit_relationship_with_provenance():
    dialog = _dialog()
    dialog.subjectCombo.setCurrentIndex(1)
    dialog.predicateCombo.setEditText("possesses")
    dialog.objectReferenceCombo.setCurrentIndex(0)
    dialog.canonCombo.setCurrentIndex(
        dialog.canonCombo.findData(CanonState.TENTATIVE)
    )
    dialog.qualifiersEdit.setPlainText("certainty: explicit")
    dialog.anchorEdit.setText("paragraph:key-transfer")
    dialog.noteEdit.setPlainText("The author recorded this manually.")

    assertion = dialog.assertion

    assert assertion.id == "assertion-1"
    assert assertion.subject == StoryReference("entity", "mara")
    assert assertion.object.reference == StoryReference(
        "document", "scene-18"
    )
    assert assertion.canon_state is CanonState.TENTATIVE
    assert assertion.qualifiers[0].value == "explicit"
    assert assertion.provenance.anchor == "paragraph:key-transfer"
    assert dialog.subjectCombo.accessibleName() == "Assertion subject"
    assert dialog.qualifiersEdit.accessibleName() == (
        "Assertion qualifiers as YAML"
    )


def test_assertion_dialog_parses_a_scalar_value_without_inference():
    dialog = _dialog()
    dialog.predicateCombo.setEditText("age")
    dialog.objectKindCombo.setCurrentIndex(1)
    dialog.objectValueEdit.setText("17")

    assertion = dialog.assertion

    assert assertion.object.kind is AssertionTermKind.VALUE
    assert assertion.object.value == 17
    assert assertion.subject == StoryReference("document", "scene-18")


def test_assertion_dialog_reports_validation_inline_and_focuses_the_field():
    dialog = AssertionEditorDialog(
        StoryReference("document", "scene-18"),
        (),
        id_factory=lambda: "assertion-1",
    )
    dialog.predicateCombo.setEditText("")

    dialog._validate_and_accept()

    assert dialog.errorLabel.isVisibleTo(dialog)
    assert "predicate" in dialog.errorLabel.text().casefold()
    assert dialog.focusWidget() is dialog.predicateCombo
