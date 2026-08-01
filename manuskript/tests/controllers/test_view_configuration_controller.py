from types import SimpleNamespace
from unittest.mock import MagicMock

from manuskript.controllers.view_configuration_controller import (
    ViewConfigurationController,
)


def make_controller():
    view = MagicMock()
    settings = SimpleNamespace(
        viewMode="fiction",
        viewSettings={
            "Tree": {"Text": "Nothing"},
            "Cork": {"Text": "Nothing"},
            "Outline": {"Text": "Nothing"},
        },
    )
    return ViewConfigurationController(view, settings), view, settings


def test_simple_mode_is_an_explicit_reversible_presentation_state():
    controller, view, settings = make_controller()

    controller.set_simple()

    assert settings.viewMode == "simple"
    view.select_editor_tab.assert_called_once_with()
    view.set_fiction_features_visible.assert_called_once_with(False)
    view.set_mode_checked.assert_called_once_with("simple")


def test_fiction_mode_restores_fiction_presentation():
    controller, view, settings = make_controller()

    controller.set_fiction()

    assert settings.viewMode == "fiction"
    view.set_fiction_features_visible.assert_called_once_with(True)
    view.set_mode_checked.assert_called_once_with("fiction")


def test_view_setting_change_updates_only_its_category():
    controller, view, settings = make_controller()

    controller.set_view_setting("Outline", "Text", "POV")

    assert settings.viewSettings["Outline"]["Text"] == "POV"
    assert settings.viewSettings["Tree"]["Text"] == "Nothing"
    view.refresh_category.assert_called_once_with("Outline")
