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


def test_the_registry_answers_nothing_about_the_project_itself():
    """It talks to windows. The project's settings, the parent its models
    hang off and which models signal a change were all answerable here,
    which let the project manager reach its own facts through whichever
    window happened to be primary.
    """
    registry = ProjectViewRegistry([MagicMock()])

    for absent in ("settings", "model_parent", "change_models"):
        assert not hasattr(registry, absent), absent


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
    assert registry.confirm_unsaved_changes() is None
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


def test_a_remark_lands_in_the_window_being_worked_in():
    """A save started in the second window reports there, not in the
    first window's status bar.
    """
    first, second = MagicMock(), MagicMock()
    registry = ProjectViewRegistry(
        [first, second],
        active_window_source=lambda: second.window,
    )

    registry.show_status("Saved.", 3000, 0)

    second.show_status.assert_called_once_with("Saved.", 3000, 0)
    first.show_status.assert_not_called()


def test_a_remark_falls_back_to_the_primary_when_no_window_is_active():
    first, second = MagicMock(), MagicMock()
    registry = ProjectViewRegistry(
        [first, second], active_window_source=lambda: None
    )

    registry.show_status("Saved.")

    first.show_status.assert_called_once_with("Saved.", 5000, 1)
    second.show_status.assert_not_called()


def test_the_speaking_view_is_resolved_per_call_not_captured():
    """The reported defect: the first window's presenter was taken once
    and kept, so after that window closed the project still reported
    into it.
    """
    first, second = MagicMock(), MagicMock()
    active = [first.window]
    registry = ProjectViewRegistry(
        [first, second], active_window_source=lambda: active[0]
    )

    registry.show_status("one")
    active[0] = second.window
    registry.unregister(first)
    registry.show_status("two")

    first.show_status.assert_called_once_with("one", 5000, 1)
    second.show_status.assert_called_once_with("two", 5000, 1)


def test_a_remark_with_no_views_left_is_dropped_rather_than_raising():
    """The last window can close while a save is still reporting."""
    registry = ProjectViewRegistry([])

    registry.show_status("Saved.")
