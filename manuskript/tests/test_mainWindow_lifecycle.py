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


def test_plugin_manager_remains_available_without_open_project(
        MWNoProject):
    MWNoProject.projectManager.syncUiToState()

    assert MWNoProject.menuTools.isEnabled()
    assert MWNoProject.pluginUi.manageAction.isEnabled()
    assert not MWNoProject.actToolFrequency.isEnabled()


def test_plugins_use_one_tools_menu(MWNoProject):
    plugin_menus = [
        action.menu()
        for action in MWNoProject.menuTools.actions()
        if action.menu() is not None
        and action.menu().objectName() == "menuPlugins"
    ]

    assert plugin_menus == [MWNoProject.pluginUi.menu]
    assert [
        action.text()
        for action in plugin_menus[0].actions()
        if not action.isSeparator()
    ] == ["Manage Plugins…", "Raw Plugin Data…"]
    assert not MWNoProject.pluginUi.projectPanels.rawDataAction.isEnabled()
