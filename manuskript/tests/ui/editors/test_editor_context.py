from manuskript.models.outlineItem import outlineItem


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
