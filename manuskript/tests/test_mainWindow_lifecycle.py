"""What closing a window means, and what quitting means.

Closing used to close everything, because there was only ever one real
window. The rules now, encoded here because getting them wrong loses
somebody's manuscript:

* the last workspace window closing closes the project, and only that
  close may ask about unsaved changes
* a cancelled prompt aborts the close entirely
* quit closes every workspace, asking once, and a cancel aborts the rest
* tool windows and dialogs are not workspaces: they neither keep a
  project open nor get closed by somebody else's window
"""

from unittest.mock import MagicMock, patch

from PyQt5.QtGui import QCloseEvent

from manuskript.services.window_registry import WindowRegistry


class reopened:
    """Put a closed window back, for the tests that share one.

    The main window is a session-wide singleton here, so a test that
    closes it has to leave it registered and attached the way it found
    it, or every later test inherits a window that is no longer a
    workspace.
    """

    def __init__(self, window):
        self.window = window

    def __enter__(self):
        return self.window

    def __exit__(self, *_exception):
        window = self.window
        window.windowRegistry.register(window)
        window.projectRuntime.attach(
            window.projectLifecycleView,
            workspace=window,
        )
        return False


def test_close_event_is_ignored_when_project_close_is_cancelled(MW):
    event = MagicMock()

    with patch.object(
        MW.projectManager,
        "closeProject",
        return_value=False,
    ), patch.object(MW, "closeToolWindows") as close_tools:
        MW.closeEvent(event)

    event.ignore.assert_called_once_with()
    close_tools.assert_not_called()
    # Still a workspace: a refused close changes nothing.
    assert MW in MW.windowRegistry.workspace_windows


def test_close_event_persists_window_state_after_safe_close(MWNoProject):
    event = QCloseEvent()

    with reopened(MWNoProject), patch.object(
        MWNoProject.projectManager,
        "closeProject",
        return_value=True,
    ), patch.object(
        MWNoProject,
        "closeToolWindows",
    ) as close_tools, patch.object(
        MWNoProject.windowState,
        "save",
    ) as save:
        MWNoProject.closeEvent(event)

    close_tools.assert_called_once_with()
    save.assert_called_once_with()
    assert event.isAccepted()


def test_the_last_window_closing_closes_the_project(MWNoProject):
    """One window left means its close is the project's close."""
    registry = MWNoProject.windowRegistry
    assert registry.is_last(MWNoProject)

    with reopened(MWNoProject), patch.object(
        MWNoProject.projectManager,
        "closeProject",
        return_value=True,
    ) as close_project, patch.object(MWNoProject.windowState, "save"):
        MWNoProject.closeEvent(QCloseEvent())

    close_project.assert_called_once_with()


def test_closing_one_of_several_windows_leaves_the_project_open(
        MWNoProject):
    """A workspace window is one view of a project. Putting the view
    away is not closing the manuscript.
    """
    registry = MWNoProject.windowRegistry
    other = MagicMock()
    registry.register(other)
    assert not registry.is_last(MWNoProject)

    with reopened(MWNoProject), patch.object(
        MWNoProject.projectManager,
        "closeProject",
    ) as close_project, patch.object(MWNoProject.windowState, "save"):
        MWNoProject.closeEvent(QCloseEvent())
        close_project.assert_not_called()
        assert MWNoProject not in registry.workspace_windows

    registry.unregister(other)


def test_closing_a_window_detaches_only_its_own_view(MWNoProject):
    """The project keeps running; it just stops reporting to this
    window.
    """
    registry = MWNoProject.windowRegistry
    other = MagicMock()
    registry.register(other)
    runtime = MWNoProject.projectRuntime
    assert MWNoProject.projectLifecycleView in runtime.views.views

    with reopened(MWNoProject), patch.object(
        MWNoProject.windowState, "save",
    ):
        MWNoProject.closeEvent(QCloseEvent())
        assert (
            MWNoProject.projectLifecycleView not in runtime.views.views
        )
        assert runtime.projectManager is not None

    registry.unregister(other)


def test_a_window_closes_its_own_tool_windows_only(MWNoProject):
    """Walking every top-level widget would shut another workspace's
    dialogs too; a window closes what it opened.
    """
    targets = MagicMock()
    frequency = MagicMock()
    stranger = MagicMock()
    MWNoProject.td = targets
    MWNoProject.fw = frequency

    MWNoProject.closeToolWindows()

    targets.close.assert_called_once_with()
    frequency.close.assert_called_once_with()
    stranger.close.assert_not_called()
    MWNoProject.td = None
    MWNoProject.fw = None


def test_quit_closes_every_workspace_asking_once():
    """The primary closes last, because it is the one that closes the
    project and therefore the one that asks.
    """
    registry = WindowRegistry()
    order = []

    def window(name, closes=True):
        entry = MagicMock()
        entry.isVisible.return_value = not closes
        entry.close.side_effect = lambda: order.append(name)
        return entry

    primary = window("primary")
    second = window("second")
    registry.register(primary)
    registry.register(second)

    assert registry.close_all() is True
    assert order == ["second", "primary"]


def test_a_cancelled_prompt_aborts_the_rest_of_the_quit():
    """Cancelling the save prompt must leave the application running,
    with the windows that had not closed yet still open.
    """
    registry = WindowRegistry()
    primary = MagicMock()
    primary.isVisible.return_value = True   # refused to close
    second = MagicMock()
    second.isVisible.return_value = True    # refused to close
    registry.register(primary)
    registry.register(second)

    assert registry.close_all() is False
    second.close.assert_called_once_with()
    primary.close.assert_not_called()


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
