"""Announcements reach every window; questions reach one.

The split is the whole point. A project with four windows open must
still ask about unsaved changes once, and must still update four sets of
widgets when its models are replaced.
"""

from unittest.mock import MagicMock

from manuskript.domain.project import CloseDecision
from manuskript.services.project_view_registry import (
    ProjectViewRegistry,
)


def test_announcements_reach_every_registered_view():
    first, second = MagicMock(), MagicMock()
    registry = ProjectViewRegistry([first, second])
    models = MagicMock()

    registry.install_models(models)
    registry.project_opened()
    registry.sync_to_state(True)
    registry.project_closed()

    for view in (first, second):
        view.install_models.assert_called_once_with(models)
        view.project_opened.assert_called_once_with()
        view.sync_to_state.assert_called_once_with(True)
        view.project_closed.assert_called_once_with()


def test_a_question_is_asked_of_the_primary_view_only():
    """Four windows must not mean four save prompts."""
    first, second = MagicMock(), MagicMock()
    first.confirm_unsaved_changes.return_value = CloseDecision.SAVE
    registry = ProjectViewRegistry([first, second])

    assert registry.confirm_unsaved_changes() is CloseDecision.SAVE

    first.confirm_unsaved_changes.assert_called_once_with()
    second.confirm_unsaved_changes.assert_not_called()


def test_shared_state_is_captured_once():
    """The settings hold one last tab and one set of open documents, so
    recording them per window would just overwrite them per window.
    """
    first, second = MagicMock(), MagicMock()
    registry = ProjectViewRegistry([first, second])

    registry.capture_project_state()

    first.capture_project_state.assert_called_once_with()
    second.capture_project_state.assert_not_called()


def test_change_models_comes_from_one_view():
    """Connecting the same model once per window would mark the project
    dirty once per window for every single edit.
    """
    first, second = MagicMock(), MagicMock()
    models = [MagicMock(), MagicMock()]
    first.change_models.return_value = models
    registry = ProjectViewRegistry([first, second])

    assert registry.change_models() == models
    second.change_models.assert_not_called()


def test_settings_and_model_parent_come_from_the_primary_view():
    view = MagicMock()
    registry = ProjectViewRegistry([view])

    assert registry.settings is view.settings
    assert registry.model_parent is view.model_parent


def test_the_next_view_inherits_the_primary_role():
    first, second = MagicMock(), MagicMock()
    registry = ProjectViewRegistry([first, second])

    registry.unregister(first)

    assert registry.primary is second
    registry.confirm_unsaved_changes()
    second.confirm_unsaved_changes.assert_called_once_with()


def test_a_registry_with_no_views_answers_rather_than_raising():
    """Between the last window closing and the project closing there is
    a moment with no views at all; it must not be a crash.
    """
    registry = ProjectViewRegistry()

    assert registry.primary is None
    assert registry.settings is None
    assert registry.model_parent is None
    assert registry.confirm_unsaved_changes() is None
    assert registry.change_models() == []
    assert registry.project_name() == ""
    assert registry.translate("Manuskript") == "Manuskript"
    # Announcements to nobody are silent, not errors.
    registry.project_closed()
    registry.capture_project_state()


def test_registering_the_same_view_twice_does_not_double_it():
    view = MagicMock()
    registry = ProjectViewRegistry()

    registry.register(view)
    registry.register(view)

    assert registry.views == (view,)
    registry.project_opened()
    view.project_opened.assert_called_once_with()
