import importlib
from unittest.mock import patch

from manuskript.models.outlineItem import outlineItem

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
    assert (
        editor.txtRedacText.text_editor_context
        is window.textEditorContext
    )
    assert (
        window.mainEditor.tabSplitter.editor_context
        is window.mainEditor.editor_context
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
