import importlib
from unittest.mock import patch

from PyQt5.QtWidgets import qApp

from manuskript.enums import Outline
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
        presentation_mode=(
            window.mainEditor.currentEditor().markdownPresentation.mode
        ),
        markup_profile=(
            window.mainEditor.currentEditor().markupProfile
        ),
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
    state = window.mainEditor.currentEditor().markdownPresentation

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


def test_markdown_mode_is_owned_by_each_editor_tab(MWEmptyProject):
    window = MWEmptyProject
    first_item = outlineItem(title="First")
    second_item = outlineItem(title="Second")
    window.mdlOutline.appendItem(first_item)
    window.mdlOutline.appendItem(second_item)
    first_index = window.mdlOutline.indexFromItem(first_item)
    second_index = window.mdlOutline.indexFromItem(second_item)

    window.mainEditor.setCurrentModelIndex(first_index, newTab=True)
    first_editor = window.mainEditor.currentEditor()
    window.actMarkdownLivePreview.trigger()

    window.mainEditor.setCurrentModelIndex(second_index, newTab=True)
    second_editor = window.mainEditor.currentEditor()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert (
        window.mainEditor.cmbMarkdownMode.currentText()
        == "Formatted Source"
    )

    first_editor._tabWidget.setCurrentWidget(first_editor)

    assert (
        window.mainEditor.cmbMarkdownMode.currentText()
        == "Live Preview"
    )
    assert window.actMarkdownLivePreview.isChecked()
    assert (
        first_editor.markdownModeButton.toolTip()
        == "Switch to Reading"
    )

    first_editor.markdownModeButton.click()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.READING
    )
    assert (
        first_editor.markdownModeButton.toolTip()
        == "Switch to Live Preview"
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    window.mainEditor.closeAllTabs()


def test_markdown_mode_is_independent_between_split_leaves(
        MWEmptyProject):
    window = MWEmptyProject
    window_was_visible = window.isVisible()
    window.resize(1100, 720)
    window.show()
    item = outlineItem(title="Chapter", _type="md")
    item.setData(
        Outline.text,
        "# Chapter 1\n\n"
        "**Bunker, Kyiv. June. Daytime.**\n\n"
        "First paragraph with *rendered emphasis*.\n\n"
        "Second paragraph stays independent.",
    )
    window.mdlOutline.appendItem(item)
    index = window.mdlOutline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    first_editor = window.mainEditor.currentEditor()
    first_editor.markdownPresentation.set_mode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )

    window.mainEditor.tabSplitter.split(state=1)
    second_editor = window.mainEditor.currentEditor()

    assert second_editor is not first_editor
    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )

    second_editor.markdownPresentation.set_mode(
        MarkdownPresentationMode.READING
    )
    qApp.processEvents()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.READING
    )
    assert (
        first_editor.markdownEditorHost.currentWidget()
        is first_editor.txtRedacText
    )
    assert first_editor.txtRedacText.isVisible()
    assert (
        second_editor.markdownEditorHost.currentWidget()
        is second_editor.txtRedacText.readingView
    )
    assert second_editor.txtRedacText.isHidden()
    window.mainEditor.closeAllTabs()
    if not window_was_visible:
        window.hide()
