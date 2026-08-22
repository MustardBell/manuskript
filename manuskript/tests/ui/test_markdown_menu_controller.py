from PyQt5.QtWidgets import QMainWindow, QWidget

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    MarkdownPresentationState,
    PresentationModeDefinition,
    contributed_presentation_view,
)
from manuskript.ui.markdown_menu_controller import (
    MarkdownMenuController,
    MarkdownMenuViews,
)


def controller_fixture():
    window = QMainWindow()
    menu = window.menuBar().addMenu("Markdown mode")
    controller = MarkdownMenuController(
        MarkdownMenuViews(menu=menu, action_parent=window)
    )
    return controller, window, menu


def test_markdown_menu_tracks_the_active_leaf_state():
    controller, window, menu = controller_fixture()
    state = MarkdownPresentationState(MarkdownPresentationMode.SOURCE)
    try:
        controller.attach(state)
        actions = controller.actions

        assert menu.isEnabled()
        assert actions[MarkdownPresentationMode.SOURCE].isChecked()

        state.set_mode(MarkdownPresentationMode.READING)

        assert actions[MarkdownPresentationMode.READING].isChecked()
    finally:
        controller.dispose()
        window.close()


def test_markdown_menu_routes_mode_intent_and_allowed_modes():
    controller, window, _menu = controller_fixture()
    state = MarkdownPresentationState()
    try:
        controller.attach(state)
        state.set_allowed_modes((
            MarkdownPresentationMode.SOURCE,
            MarkdownPresentationMode.LIVE_PREVIEW,
        ))
        actions = controller.actions

        controller.set_mode(MarkdownPresentationMode.LIVE_PREVIEW)

        assert state.mode is MarkdownPresentationMode.LIVE_PREVIEW
        assert actions[MarkdownPresentationMode.SOURCE].isEnabled()
        assert actions[MarkdownPresentationMode.LIVE_PREVIEW].isEnabled()
        assert MarkdownPresentationMode.FORMATTED_SOURCE not in actions
        assert MarkdownPresentationMode.READING not in actions
    finally:
        controller.dispose()
        window.close()


def test_detaching_disables_the_menu_and_ignores_the_old_leaf():
    controller, window, menu = controller_fixture()
    state = MarkdownPresentationState()
    try:
        controller.attach(state)
        old_reading = controller.actions[MarkdownPresentationMode.READING]
        controller.attach(None)
        old_reading.setChecked(False)

        state.set_mode(MarkdownPresentationMode.SOURCE)
        old_reading.trigger()

        assert not menu.isEnabled()
        assert state.mode is MarkdownPresentationMode.SOURCE
    finally:
        controller.dispose()
        window.close()


def test_main_window_delegates_markdown_menu_state(MW):
    assert MW.markdownMenu.views.menu is MW.menuMarkdownMode
    assert not hasattr(MW, "setMarkdownPresentationMode")
    assert not hasattr(MW, "attachMarkdownPresentationState")
    assert not hasattr(MW, "syncMarkdownPresentationActions")
    assert not hasattr(MW, "syncMarkdownPresentationModes")


def test_menu_builds_a_contributed_mode_from_the_leaf_catalogue():
    controller, window, menu = controller_fixture()
    state = MarkdownPresentationState()
    definition = PresentationModeDefinition(
        "example.graph",
        "Story graph",
        contributed_presentation_view,
        owner_id="example.plugin",
        widget_factory=QWidget,
    )
    try:
        controller.attach(state)
        state.set_allowed_modes((MarkdownPresentationMode.SOURCE, definition))

        action = controller.actions["example.graph"]
        assert [item.text() for item in menu.actions()] == [
            "Source", "Story graph",
        ]

        action.trigger()

        assert state.mode == "example.graph"
        assert action.isChecked()
    finally:
        controller.dispose()
        window.close()
