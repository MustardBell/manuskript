from unittest.mock import MagicMock, patch

from PyQt5.QtGui import QCloseEvent


def test_close_event_is_ignored_when_project_close_is_cancelled(MW):
    event = MagicMock()

    with patch.object(
        MW.projectManager,
        "closeProject",
        return_value=False,
    ), patch.object(MW, "closeAuxiliaryWindows") as close_auxiliary:
        MW.closeEvent(event)

    event.ignore.assert_called_once_with()
    close_auxiliary.assert_not_called()


def test_close_event_persists_window_state_after_safe_close(MWNoProject):
    event = QCloseEvent()

    with patch.object(
        MWNoProject.projectManager,
        "closeProject",
        return_value=True,
    ), patch.object(
        MWNoProject,
        "closeAuxiliaryWindows",
    ) as close_auxiliary, patch.object(
        MWNoProject.windowState,
        "save",
    ) as save:
        MWNoProject.closeEvent(event)

    close_auxiliary.assert_called_once_with()
    save.assert_called_once_with()
    assert event.isAccepted()


def test_close_auxiliary_windows_closes_every_other_top_level_window(
        MWNoProject):
    first = MagicMock()
    second = MagicMock()

    with patch(
        "manuskript.mainWindow.QApplication.topLevelWidgets",
        return_value=[first, MWNoProject, second],
    ):
        MWNoProject.closeAuxiliaryWindows()

    first.close.assert_called_once_with()
    second.close.assert_called_once_with()
