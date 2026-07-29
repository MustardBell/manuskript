import importlib
from unittest.mock import patch

from manuskript.models.outlineItem import outlineItem
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)

main_editor_module = importlib.import_module(
    "manuskript.ui.editors.mainEditor"
)


def test_opened_editor_tab_inherits_project_context(MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)

    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()

    assert editor.editor_context is window.mainEditor.editor_context
    assert editor.outline_context is editor.editor_context.outline_views
    assert editor.corkView.outline_context is editor.outline_context
    assert editor.outlineView.outline_context is editor.outline_context
    assert editor.settings is window.settingsManager
    assert window.mdlOutline.settings is window.settingsManager
    assert item.settings is window.settingsManager
    assert window.lstPlots.settings is window.settingsManager
    assert window.lstOutlinePlots.settings is window.settingsManager
    assert (
        editor.txtRedacText.text_editor_context
        is window.textEditorContext
    )
    assert (
        window.mainEditor.tabSplitter.editor_context
        is window.mainEditor.editor_context
    )
    assert (
        window.mainEditor.tabSplitter.settings
        is window.settingsManager
    )
    assert window.mainEditor.tabSplitter.tabOpenIndexes() == [item.ID()]

    window.mainEditor.tabSplitter.split(state=1)
    assert (
        window.mainEditor.tabSplitter.secondTab.editor_context
        is window.mainEditor.editor_context
    )

    window.mainEditor.closeAllTabs()


def test_full_screen_editor_receives_existing_editor_context(
        MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter", _type="md")
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)

    with patch.object(
        main_editor_module,
        "QDesktopWidget",
    ) as desktop, patch.object(
        main_editor_module,
        "fullScreenEditor",
    ) as full_screen:
        desktop.return_value.screenNumber.return_value = 0

        window.mainEditor.showFullScreen()

    full_screen.assert_called_once_with(
        index,
        settings=window.settingsManager,
        text_editor_context=window.textEditorContext,
        screenNumber=0,
    )
    window.mainEditor.closeAllTabs()


def test_active_editor_selection_sync_refreshes_main_editor(
        MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()

    with patch.object(window.mainEditor, "tabChanged") as tab_changed:
        editor._syncActiveEditorSelection()

    tab_changed.assert_called_once_with()
    window.mainEditor.closeAllTabs()


def test_markdown_modes_are_visible_and_synchronized(MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    manuscript_editor = window.mainEditor.currentEditor().txtRedacText
    selector = window.mainEditor.cmbMarkdownMode
    state = window.textEditorContext.markdown_presentation

    assert (
        window.menuMarkdownMode.menuAction()
        in window.menuView.actions()
    )
    assert selector.isEnabled()
    assert selector.currentText() == "Formatted Source"

    selector.setCurrentIndex(0)

    assert state.mode is MarkdownPresentationMode.SOURCE
    assert window.actMarkdownSource.isChecked()

    window.actMarkdownFormattedSource.trigger()

    assert state.mode is MarkdownPresentationMode.FORMATTED_SOURCE
    assert selector.currentText() == "Formatted Source"

    window.actMarkdownReading.trigger()

    assert state.mode is MarkdownPresentationMode.READING
    assert selector.currentText() == "Reading"
    assert (
        manuscript_editor.presentationMode
        is MarkdownPresentationMode.READING
    )
    assert (
        window.txtSummarySentence.presentationMode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert window.txtSummarySentence.readingView is None
    window.mainEditor.closeAllTabs()
