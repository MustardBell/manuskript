from manuskript.domain.entity_catalog import EntityReferenceChoice
from manuskript.domain.story_assertions import (
    AssertionTermKind,
    CanonState,
    StoryReference,
    TemporalAxis,
    TemporalPoint,
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


def test_assertion_dialog_builds_narrative_temporal_validity_accessibly():
    choices = (
        (
            "Scene 4 — narrative order",
            TemporalPoint.narrative("document", "scene-4"),
        ),
        (
            "Scene 8 — narrative order",
            TemporalPoint.narrative("document", "scene-8"),
        ),
    )
    dialog = AssertionEditorDialog(
        StoryReference("document", "scene-18"),
        (),
        id_factory=lambda: "assertion-1",
        temporal_choices=choices,
        temporal_enabled=True,
    )
    dialog.validityAxisCombo.setCurrentIndex(
        dialog.validityAxisCombo.findData(TemporalAxis.NARRATIVE)
    )
    dialog.validityFromCombo.setCurrentIndex(1)
    dialog.validityUntilCombo.setCurrentIndex(2)

    assertion = dialog.assertion

    assert assertion.validity.valid_from == choices[0][1]
    assert assertion.validity.valid_until == choices[1][1]
    assert dialog.validityFromCombo.accessibleName() == "Valid from"


def test_assertion_dialog_accepts_custom_iso_story_time():
    dialog = AssertionEditorDialog(
        StoryReference("document", "scene-18"),
        (),
        id_factory=lambda: "assertion-1",
        temporal_enabled=True,
    )
    dialog.validityAxisCombo.setCurrentIndex(
        dialog.validityAxisCombo.findData(TemporalAxis.STORY)
    )
    dialog.validityFromCombo.setEditText("1914-07-28T09:30:00+02:00")

    assert dialog.assertion.validity.valid_from.value == (
        "1914-07-28T09:30:00+02:00"
    )
