"""A split document pane can leave without moving its whole Editor."""

from dataclasses import replace
from unittest.mock import patch

from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent, QTextCursor
from PyQt5.QtWidgets import qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.panels.core import EDITOR
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


def _open_document(window, title, text="alpha beta gamma"):
    item = outlineItem(title=title, _type="md")
    item.setData(Outline.text, text)
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    return item


def test_one_split_pane_moves_to_a_distinct_editor_workspace(
        MWEmptyProject):
    window = MWEmptyProject
    source = window.mainEditor
    source.closeAllTabs()
    item = _open_document(
        window,
        "Pane transfer",
        "\n\n".join(
            "Paragraph {} is long enough to exercise view-local scroll."
            .format(number)
            for number in range(160)
        ),
    )
    source.tabSplitter.split(state=1)
    pane = source.tabSplitter.secondTab
    tab = pane.tab.currentWidget()
    tab.markdownPresentation.set_mode(MarkdownPresentationMode.SOURCE)
    cursor = tab.txtRedacText.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(5, QTextCursor.KeepAnchor)
    tab.txtRedacText.setTextCursor(cursor)
    window.resize(900, 600)
    window.show()
    qApp.processEvents()
    source_scroll = tab.txtRedacText.verticalScrollBar()
    source_scroll.setValue(min(120, source_scroll.maximum()))
    expected_scroll = source_scroll.value()
    assert expected_scroll > 0
    before = set(window.windowRegistry.workspace_windows)

    destination = window.editorPaneTransfer.move_pane(pane)
    qApp.processEvents()
    created = [
        workspace
        for workspace in window.windowRegistry.workspace_windows
        if workspace not in before
    ]
    try:
        assert destination is not None
        assert created == [destination]
        assert set(destination.surfaceHost.instances) == {EDITOR}
        assert sum(
            leaf.tab.count() for leaf in source.allTabSplitters()
        ) == 1
        assert source.tabSplitter.secondTab is None

        moved = destination.mainEditor.currentEditor()
        assert moved.currentID == item.ID()
        assert moved.markdownPresentation.mode is MarkdownPresentationMode.SOURCE
        assert moved.txtRedacText.textCursor().anchor() == 1
        assert moved.txtRedacText.textCursor().position() == 5
        assert moved.txtRedacText.verticalScrollBar().value() == (
            expected_scroll
        )
        assert moved.parentWidget() is not tab.parentWidget()

        moved.txtRedacText.moveCursor(QTextCursor.End)
        moved.txtRedacText.insertPlainText(" shared")
        moved.txtRedacText.submit()
        qApp.processEvents()
        assert source.currentEditor().txtRedacText.toPlainText().endswith(
            " shared"
        )
    finally:
        for workspace in created:
            workspace.close()


def test_every_editor_pane_exposes_an_accessible_working_tear_off_command(
        MWEmptyProject):
    editor = MWEmptyProject.mainEditor
    editor.closeAllTabs()
    _open_document(MWEmptyProject, "Accessible pane transfer")
    pane = editor.tabSplitter

    assert pane.btnTearOff.isEnabled()
    assert not pane.btnTearOff.icon().isNull()
    assert pane.btnTearOff.accessibleName()
    assert "new window" in pane.btnTearOff.toolTip()
    assert MWEmptyProject.editorPaneTransfer.action.objectName() == (
        "actMoveEditorPaneToNewWindow"
    )
    with patch.object(editor, "tearOffPane") as move:
        pane.btnTearOff.click()

    move.assert_called_once_with(pane)


def test_failed_destination_creation_leaves_the_source_pane_intact(
        MWEmptyProject):
    window = MWEmptyProject
    controller = window.editorPaneTransfer
    window.mainEditor.closeAllTabs()
    _open_document(window, "Rollback pane transfer")
    pane = window.mainEditor.tabSplitter
    before = tuple(
        pane.tab.widget(index) for index in range(pane.tab.count())
    )
    original_views = controller.views

    def fail(_intent):
        raise RuntimeError("destination refused")

    controller.views = replace(original_views, create_workspace=fail)
    try:
        assert controller.move_pane(pane) is None
    finally:
        controller.views = original_views

    assert tuple(
        pane.tab.widget(index) for index in range(pane.tab.count())
    ) == before


def test_dragging_a_tab_beyond_its_bar_uses_the_same_pane_command(
        MWEmptyProject):
    editor = MWEmptyProject.mainEditor
    editor.closeAllTabs()
    _open_document(MWEmptyProject, "Dragged pane transfer")
    pane = editor.tabSplitter
    tab_bar = pane.tab.tabBar()
    start = tab_bar.tabRect(0).center()
    outside = QPoint(start.x(), tab_bar.height() + 40)
    press = QMouseEvent(
        QEvent.MouseButtonPress,
        start,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    move_event = QMouseEvent(
        QEvent.MouseMove,
        outside,
        Qt.NoButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    class IgnoredDrag:
        def __init__(self, _source):
            pass

        def setMimeData(self, _mime_data):
            pass

        def setPixmap(self, _pixmap):
            pass

        def setHotSpot(self, _point):
            pass

        def exec_(self, _action):
            return Qt.IgnoreAction

        def deleteLater(self):
            pass

    assert pane._tabBarEvent(press) is False
    with patch(
            "manuskript.ui.editors.tabSplitter.QDrag", IgnoredDrag):
        with patch.object(editor, "tearOffPane") as tear_off:
            assert pane._tabBarEvent(move_event) is True

    tear_off.assert_called_once()
    assert tear_off.call_args.args[0] is pane
