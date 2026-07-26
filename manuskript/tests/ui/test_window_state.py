from unittest.mock import MagicMock

from manuskript.services.window_state import ApplicationWindowState
from manuskript.ui.window_state import MainWindowStateController


def make_window():
    window = MagicMock()
    window.dckNavigation.objectName.return_value = "navigation"
    window.dckCheatSheet.objectName.return_value = "cheat-sheet"
    window.dckSearch.objectName.return_value = "search"
    return window


def test_window_state_controller_restores_widgets_and_loaded_docks():
    window = make_window()
    store = MagicMock()
    store.load.return_value = ApplicationWindowState(
        geometry=b"geometry",
        window_state=b"window",
        docks={
            "navigation": False,
            "cheat-sheet": True,
            "search": False,
        },
        metadata=["true", "false", False],
        revisions=["false", True],
        redaction_horizontal=b"horizontal",
        redaction_vertical=b"vertical",
        toolbar=[("group", "title", True)],
    )
    controller = MainWindowStateController(window, store)

    controller.restore()
    controller.restore_toolbar(window.toolbar)
    controller.restore_project_docks()

    window.restoreGeometry.assert_called_once_with(b"geometry")
    window.restoreState.assert_called_once_with(b"window")
    window.redacMetadata.restoreState.assert_called_once_with(
        [True, False, False]
    )
    window.redacMetadata.revisions.restoreState.assert_called_once_with(
        [False, True]
    )
    window.toolbar.restoreState.assert_called_once_with(
        [("group", "title", True)]
    )
    window.dckNavigation.setVisible.assert_called_once_with(False)
    window.dckCheatSheet.setVisible.assert_called_once_with(True)
    window.dckSearch.setVisible.assert_called_once_with(False)


def test_first_welcome_switch_preserves_loaded_dock_visibility():
    window = make_window()
    store = MagicMock()
    store.load.return_value = ApplicationWindowState(
        docks={
            "navigation": False,
            "cheat-sheet": True,
            "search": True,
        }
    )
    controller = MainWindowStateController(window, store)
    controller.restore()

    controller.hide_project_docks()
    controller.restore_project_docks()

    window.dckNavigation.isVisible.assert_not_called()
    window.dckNavigation.setVisible.assert_called_with(False)
    window.dckCheatSheet.setVisible.assert_called_with(True)
    window.dckSearch.setVisible.assert_called_with(True)


def test_window_state_controller_captures_current_project_layout():
    window = make_window()
    store = MagicMock()
    window.stack.currentIndex.return_value = 1
    window.dckNavigation.isVisible.return_value = True
    window.dckCheatSheet.isVisible.return_value = False
    window.dckSearch.isVisible.return_value = True
    window.saveGeometry.return_value = b"geometry"
    window.saveState.return_value = b"window"
    window.redacMetadata.saveState.return_value = [True]
    window.redacMetadata.revisions.saveState.return_value = [False]
    window.splitterRedacH.saveState.return_value = b"horizontal"
    window.splitterRedacV.saveState.return_value = b"vertical"
    window.toolbar.saveState.return_value = [("group", "title", False)]
    controller = MainWindowStateController(window, store)

    controller.save()

    state = store.save.call_args.args[0]
    assert state.geometry == b"geometry"
    assert state.window_state == b"window"
    assert state.docks == {
        "navigation": True,
        "cheat-sheet": False,
        "search": True,
    }
    assert state.metadata == [True]
    assert state.revisions == [False]
    assert state.redaction_horizontal == b"horizontal"
    assert state.redaction_vertical == b"vertical"
    assert state.toolbar == [("group", "title", False)]
