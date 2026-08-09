from PyQt5.QtWidgets import QAction, QMainWindow

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    MarkdownPresentationState,
)
from manuskript.ui.markdown_menu_controller import (
    MarkdownMenuController,
    MarkdownMenuViews,
)


def controller_fixture():
    window = QMainWindow()
    menu = window.menuBar().addMenu("Markdown mode")
    actions = {}
    for mode in MarkdownPresentationMode:
        action = QAction(mode.value, window)
        action.setCheckable(True)
        menu.addAction(action)
        actions[mode] = action
    controller = MarkdownMenuController(
        MarkdownMenuViews(menu=menu, actions=actions)
    )
    return controller, window, menu, actions


def test_markdown_menu_tracks_the_active_leaf_state():
    controller, window, menu, actions = controller_fixture()
    state = MarkdownPresentationState(MarkdownPresentationMode.SOURCE)
    try:
        controller.attach(state)

        assert menu.isEnabled()
        assert actions[MarkdownPresentationMode.SOURCE].isChecked()

        state.set_mode(MarkdownPresentationMode.READING)

        assert actions[MarkdownPresentationMode.READING].isChecked()
    finally:
        controller.dispose()
        window.close()


def test_markdown_menu_routes_mode_intent_and_allowed_modes():
    controller, window, _menu, actions = controller_fixture()
    state = MarkdownPresentationState()
    try:
        controller.attach(state)
        state.set_allowed_modes((
            MarkdownPresentationMode.SOURCE,
            MarkdownPresentationMode.LIVE_PREVIEW,
        ))

        controller.set_mode(MarkdownPresentationMode.LIVE_PREVIEW)

        assert state.mode is MarkdownPresentationMode.LIVE_PREVIEW
        assert actions[MarkdownPresentationMode.SOURCE].isEnabled()
        assert actions[MarkdownPresentationMode.LIVE_PREVIEW].isEnabled()
        assert not actions[
            MarkdownPresentationMode.FORMATTED_SOURCE
        ].isEnabled()
        assert not actions[MarkdownPresentationMode.READING].isEnabled()
    finally:
        controller.dispose()
        window.close()


def test_detaching_disables_the_menu_and_ignores_the_old_leaf():
    controller, window, menu, actions = controller_fixture()
    state = MarkdownPresentationState()
    try:
        controller.attach(state)
        controller.attach(None)
        actions[MarkdownPresentationMode.READING].setChecked(False)

        state.set_mode(MarkdownPresentationMode.READING)

        assert not menu.isEnabled()
        assert not actions[MarkdownPresentationMode.READING].isChecked()
    finally:
        controller.dispose()
        window.close()


def test_main_window_delegates_markdown_menu_state(MW):
    assert MW.markdownMenu.views.menu is MW.menuMarkdownMode
    assert not hasattr(MW, "setMarkdownPresentationMode")
    assert not hasattr(MW, "attachMarkdownPresentationState")
    assert not hasattr(MW, "syncMarkdownPresentationActions")
    assert not hasattr(MW, "syncMarkdownPresentationModes")
