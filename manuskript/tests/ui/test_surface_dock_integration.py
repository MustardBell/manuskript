"""Writing surfaces remain docks, but tear off into real workspaces."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, qApp

from manuskript.panels.core import EDITOR, GENERAL


def test_editor_is_an_independent_native_dock(MWEmptyProject):
    window = MWEmptyProject
    editor = window.surfaceHost.instance(EDITOR)

    assert isinstance(editor.container, QDockWidget)
    assert editor.container.parentWidget() is window
    assert editor.container.widget() is editor.widget
    assert window.panelHost.instance(EDITOR) is None
    assert window.tabMain.indexOf(editor.widget) == -1
    assert editor.container.features() & (
        QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
    )


def test_navigating_to_general_does_not_replace_a_visible_editor(
        MWEmptyProject):
    window = MWEmptyProject
    assert window.activatePanel(EDITOR)
    editor = window.surfaceHost.instance(EDITOR).container
    assert not editor.isHidden()

    assert window.activatePanel(GENERAL)

    assert not editor.isHidden()
    assert not window.surfaceHost.instance(GENERAL).container.isHidden()
    assert window.surfaceHost.current() == GENERAL


def test_tearing_off_editor_transfers_it_to_a_peer_main_window(
        MWEmptyProject):
    source = MWEmptyProject
    source.activatePanel(EDITOR)
    original = source.surfaceHost.instance(EDITOR)
    widget = original.widget
    dock = original.container
    before = set(source.windowRegistry.workspace_windows)

    dock.setFloating(True)
    for _turn in range(4):
        qApp.processEvents()

    added = set(source.windowRegistry.workspace_windows) - before
    assert len(added) == 1
    destination = added.pop()
    arrived = destination.surfaceHost.instance(EDITOR)
    try:
        assert source.surfaceHost.instance(EDITOR) is None
        assert arrived.widget is widget
        assert arrived.container.parentWidget() is destination
        assert not arrived.container.isFloating()
        assert destination.parentWidget() is None
        flags = destination.windowFlags()
        assert flags & Qt.WindowMinimizeButtonHint
        assert flags & Qt.WindowMaximizeButtonHint
    finally:
        # Return the living shared fixture surface before closing the sparse
        # destination, otherwise later tests would correctly have no Editor.
        returned = destination.surfaceHost.detach(EDITOR)
        source.surfaceHost.attach(returned)
        source.activatePanel(EDITOR)
        destination.close()
        qApp.processEvents()
