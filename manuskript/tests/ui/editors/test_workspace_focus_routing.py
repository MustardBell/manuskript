from unittest.mock import MagicMock

from PyQt5.QtWidgets import qApp

from manuskript.ui.editors.editorWidget import editorWidget
from manuskript.ui.editors.editorTextHistory import EditorTextHistory
from manuskript.ui.editors.tabSplitter import tabSplitter


def test_editor_text_history_uses_workspace_focus_and_releases_it():
    focus = MagicMock()
    owner = MagicMock()
    history = EditorTextHistory(owner, focus_source=focus)

    focus.subscribe.assert_called_once_with(history._focusChanged)

    history.dispose()

    focus.unsubscribe.assert_called_once_with(history._focusChanged)
    assert history._owner is None


def test_editor_text_history_resolves_the_editor_containing_focus():
    focus = MagicMock()
    owner = MagicMock()
    canonical = MagicMock()
    other = MagicMock()
    child = MagicMock()
    child.parentWidget.return_value = canonical
    focus.focused_widget = child
    owner.txtRedacText = canonical
    owner.txtEdits = [other]
    history = EditorTextHistory(owner, focus_source=focus)

    assert history.activeEditor() is canonical

    history.dispose()


def test_standalone_editor_history_falls_back_without_global_focus():
    owner = MagicMock()
    canonical = MagicMock()
    owner.txtRedacText = canonical
    owner.txtEdits = []
    history = EditorTextHistory(owner)

    assert history.activeEditor() is canonical


def test_editor_tab_unsubscribes_before_disposing_source_editors():
    events = []
    history = MagicMock()
    history.dispose.side_effect = lambda: events.append("unsubscribed")
    source = MagicMock()
    source.dispose.side_effect = (
        lambda: events.append("editor disposed")
    )
    tab = MagicMock()
    tab.textHistory = history
    tab.sourceEditors.return_value = (source,)

    editorWidget.dispose(tab)

    assert events == ["unsubscribed", "editor disposed"]


def test_split_pane_replaces_and_releases_workspace_focus_source():
    main_editor = MagicMock()
    first = MagicMock()
    second = MagicMock()
    pane = tabSplitter(mainEditor=main_editor)
    try:
        pane.set_focus_source(first)
        pane.set_focus_source(second)
        pane.set_focus_source(None)

        first.subscribe.assert_called_once_with(pane.focusChanged)
        first.unsubscribe.assert_called_once_with(pane.focusChanged)
        second.subscribe.assert_called_once_with(pane.focusChanged)
        second.unsubscribe.assert_called_once_with(pane.focusChanged)
    finally:
        pane.deleteLater()


def test_real_focus_switches_the_active_split_pane(MWEmptyProject):
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    was_visible = window.isVisible()
    window.resize(1000, 700)
    window.show()
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    from manuskript.panels.core import EDITOR
    window.activatePanel(EDITOR)
    root = window.mainEditor.tabSplitter
    model = window.projectRuntime.models.outline
    first_item = outlineItem(title="First focus", _type="md")
    second_item = outlineItem(title="Second focus", _type="md")
    model.appendItem(first_item)
    model.appendItem(second_item)
    root.split(state=1)
    try:
        window.mainEditor.setCurrentModelIndex(
            model.indexFromItem(first_item),
            newTab=True,
            tabWidget=root.tab,
        )
        window.mainEditor.setCurrentModelIndex(
            model.indexFromItem(second_item),
            newTab=True,
            tabWidget=root.secondTab.tab,
        )
        first_editor = root.tab.currentWidget().txtRedacText
        second_editor = root.secondTab.tab.currentWidget().txtRedacText

        # Offscreen Qt plugins disagree on whether a synthetic viewport
        # click also performs the window-system focus transfer. Request it,
        # then verify the editor's click port makes routing deterministic.
        first_editor.setFocus(Qt.MouseFocusReason)
        QTest.mouseClick(first_editor.viewport(), Qt.LeftButton)
        QTest.qWait(20)
        assert root.focusTab == 1
        assert window.mainEditor.currentEditor().txtRedacText is first_editor

        second_editor.setFocus(Qt.MouseFocusReason)
        QTest.mouseClick(second_editor.viewport(), Qt.LeftButton)
        QTest.qWait(20)
        assert root.focusTab == 2
        assert window.mainEditor.currentEditor().txtRedacText is second_editor
    finally:
        root.closeSplit()
        while root.tab.count():
            root.closeTab(0)
        if not was_visible:
            window.hide()


def test_closing_the_focused_tab_releases_workspace_command_targets(
        MWEmptyProject):
    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    model = window.projectRuntime.models.outline
    item = outlineItem(title="Disposable focus", _type="md")
    model.appendItem(item)
    window.mainEditor.setCurrentModelIndex(
        model.indexFromItem(item),
        newTab=True,
    )
    editor = window.mainEditor.currentEditor().txtRedacText
    editor.text_editor_context.focus_received(editor)

    window.mainEditor.closeAllTabs()

    assert window.workspaceFocus.focused_widget is None
    assert window.workspaceFocus.markup_target is None


def test_closing_a_tab_cancels_deferred_editor_callbacks(MWEmptyProject):
    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    model = window.projectRuntime.models.outline
    item = outlineItem(title="Deferred callbacks", _type="md")
    model.appendItem(item)
    window.mainEditor.setCurrentModelIndex(
        model.indexFromItem(item),
        newTab=True,
    )
    source = window.mainEditor.currentEditor().txtRedacText
    source.updateTimer.start()
    source.scheduleInteractionRectUpdate()
    assert source.updateTimer.isActive()
    assert source.interactionRectUpdateTimer.isActive()

    window.mainEditor.closeAllTabs()

    assert source.updateTimer is None
    assert not source.interactionRectUpdateTimer.isActive()
    # Both callbacks used to reach a document/highlighter already detached
    # by closeTab(), which newer PyQt treats as a fatal slot exception.
    qApp.processEvents()
