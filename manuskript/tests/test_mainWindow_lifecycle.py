from unittest.mock import MagicMock, patch

from PyQt5.QtGui import QCloseEvent


def test_close_event_is_ignored_when_project_close_is_cancelled(MW):
    event = MagicMock()

    with patch.object(MW.projectManager, "closeProject", return_value=False):
        MW.closeEvent(event)

    event.ignore.assert_called_once_with()


def test_close_event_persists_window_state_after_safe_close(MWNoProject):
    event = QCloseEvent()

    with patch.object(
        MWNoProject.projectManager,
        "closeProject",
        return_value=True,
    ), patch.object(MWNoProject.windowState, "save") as save:
        MWNoProject.closeEvent(event)

    save.assert_called_once_with()
    assert event.isAccepted()
