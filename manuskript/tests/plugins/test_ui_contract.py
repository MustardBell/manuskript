import pytest

from manuskript.plugins.ui_contract import (
    UiChoice,
    UiControl,
    UiControlKind,
    UiDocument,
)
from manuskript.plugins.values import api_value_codec


def test_ui_document_round_trips_as_a_language_neutral_value():
    document = UiDocument("example.settings", 2, (
        UiControl(
            "mode",
            UiControlKind.CHOICE,
            "Presentation",
            description="How the result is shown.",
            value="compact",
            choices=(
                UiChoice("Compact", "compact"),
                UiChoice("Detailed", "detailed"),
            ),
        ),
    ))

    codec = api_value_codec()
    assert codec.decode(codec.encode(document)) == document
    assert codec.schema_document["records"]["ui_control"]["fields"]


def test_interactive_controls_cannot_be_unlabelled():
    with pytest.raises(ValueError, match="visible label"):
        UiControl("mystery", UiControlKind.TEXT)


def test_control_ids_are_unique_across_nested_groups():
    with pytest.raises(ValueError, match="unique"):
        UiDocument("example.panel", 0, (
            UiControl("name", UiControlKind.TEXT, "Name"),
            UiControl(
                "details",
                UiControlKind.GROUP,
                "Details",
                children=(
                    UiControl("name", UiControlKind.TEXT, "Other name"),
                ),
            ),
        ))


def test_choice_and_table_shapes_are_validated_before_rendering():
    with pytest.raises(ValueError, match="choices"):
        UiControl("mode", UiControlKind.CHOICE, "Mode")
    with pytest.raises(ValueError, match="columns"):
        UiControl("results", UiControlKind.TABLE, "Results")
