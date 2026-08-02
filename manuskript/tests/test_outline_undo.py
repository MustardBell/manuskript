"""Deleting part of a manuscript must be reversible."""

from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QUndoStack, qApp

from manuskript.commands.outline_commands import RemoveOutlineItemsCommand
from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem


def scene(model, title, parent=QModelIndex(), text="Once upon a time."):
    """Append a text item, then fill it in.

    Data must be set after insertion: setData emits dataChanged, which
    resolves the item's index, and an item outside the tree has none.
    """
    item = outlineItem(model, title=title, _type="md")
    model.appendItem(item, parent)
    item.setData(Outline.text, text)
    return item


def titles(item):
    return [child.title() for child in item.children()]


def test_deleting_a_top_level_item_can_be_undone(MWEmptyProject):
    model = MWEmptyProject.mdlOutline
    item = scene(model, "Chapter One")
    before = titles(model.rootItem)
    stack = QUndoStack()

    stack.push(RemoveOutlineItemsCommand(
        model, [model.indexFromItem(item)]))

    assert "Chapter One" not in titles(model.rootItem)

    stack.undo()

    assert titles(model.rootItem) == before
    # The same object comes back, so its ID and text survive.
    restored = next(
        c for c in model.rootItem.children() if c.title() == "Chapter One")
    assert restored is item
    assert restored.data(Outline.text) == "Once upon a time."

    stack.redo()

    assert "Chapter One" not in titles(model.rootItem)


def test_undo_restores_position_not_just_presence(MWEmptyProject):
    model = MWEmptyProject.mdlOutline
    made = [scene(model, name) for name in ("A", "B", "C")]
    before = titles(model.rootItem)
    stack = QUndoStack()

    # Remove the middle one; undo must put it back between A and C.
    stack.push(RemoveOutlineItemsCommand(
        model, [model.indexFromItem(made[1])]))
    stack.undo()

    assert titles(model.rootItem) == before


def test_a_folder_and_its_child_are_restored_in_the_right_order(
        MWEmptyProject):
    """The hard case: the parent must exist again before the child returns."""
    model = MWEmptyProject.mdlOutline
    folder = outlineItem(model, title="Act", _type="folder")
    model.appendItem(folder)
    child = scene(model, "Scene in act", model.indexFromItem(folder))
    stack = QUndoStack()

    stack.push(RemoveOutlineItemsCommand(model, [
        model.indexFromItem(folder),
        model.indexFromItem(child),
    ]))

    assert "Act" not in titles(model.rootItem)

    stack.undo()

    restored = next(
        c for c in model.rootItem.children() if c.title() == "Act")
    assert titles(restored) == ["Scene in act"]


def test_deleting_several_siblings_restores_all_of_them(MWEmptyProject):
    model = MWEmptyProject.mdlOutline
    folder = outlineItem(model, title="Bulk", _type="folder")
    model.appendItem(folder)
    parent_index = model.indexFromItem(folder)
    for name in ("one", "two", "three"):
        scene(model, name, parent_index)
    before = titles(folder)
    stack = QUndoStack()

    stack.push(RemoveOutlineItemsCommand(model, [
        model.indexFromItem(child) for child in list(folder.children())
    ]))

    assert titles(folder) == []

    stack.undo()

    assert titles(folder) == before


def test_the_command_names_what_it_deleted(MWEmptyProject):
    model = MWEmptyProject.mdlOutline
    item = scene(model, "Nameable")

    single = RemoveOutlineItemsCommand(
        model, [model.indexFromItem(item)])

    assert "Nameable" in single.text()

    other = scene(model, "Second")
    both = RemoveOutlineItemsCommand(model, [
        model.indexFromItem(item), model.indexFromItem(other)])

    assert "2" in both.text()


def test_an_empty_selection_produces_nothing_to_undo(MWEmptyProject):
    model = MWEmptyProject.mdlOutline

    command = RemoveOutlineItemsCommand(model, [])

    assert command.isEmpty()


def test_outline_views_delete_through_the_undo_stack(MWEmptyProject):
    """The view path, not just the command in isolation."""
    window = MWEmptyProject
    model = window.mdlOutline
    item = scene(model, "Deleted from the tree")
    tree = window.treeRedacOutline
    tree.setCurrentIndex(model.indexFromItem(item))
    settings = window.settingsManager
    previous = settings.dontShowDeleteWarning
    settings.dontShowDeleteWarning = True  # skip the modal

    try:
        tree.removeSelection()

        assert "Deleted from the tree" not in titles(model.rootItem)
        assert window.undoStack.canUndo()

        window.undoStack.undo()

        assert "Deleted from the tree" in titles(model.rootItem)
    finally:
        settings.dontShowDeleteWarning = previous
        window.undoStack.clear()


def test_undo_is_scoped_to_the_outline_not_the_whole_window(MWEmptyProject):
    """Ctrl+Z must not be stolen from the text editors.

    A window-level shortcut is dispatched before the focused widget sees the
    key, so binding undo on the window would break typing undo.
    """
    window = MWEmptyProject
    tree = window.treeRedacOutline

    shortcuts = {
        action.shortcut().toString()
        for action in window.actions()
        if not action.shortcut().isEmpty()
    }
    assert QKeySequence(QKeySequence.Undo).toString() not in shortcuts

    tree_undo = [
        action for action in tree.actions()
        if action.shortcut() == QKeySequence(QKeySequence.Undo)
    ]
    assert len(tree_undo) == 1
    assert tree_undo[0].shortcutContext() == Qt.WidgetWithChildrenShortcut


def test_closing_a_project_forgets_its_history(MWEmptyProject):
    """Undo must not reach across projects."""
    window = MWEmptyProject
    model = window.mdlOutline
    item = scene(model, "Belongs to this project")
    window.undoStack.push(RemoveOutlineItemsCommand(
        model, [model.indexFromItem(item)]))
    assert window.undoStack.canUndo()

    window.projectLifecycleView.prepare_close()

    assert not window.undoStack.canUndo()


def test_the_editor_buttons_undo_typing_not_the_outline(MWEmptyProject):
    """The buttons sit in a text editor, so they reverse editing.

    Outline structure has its own history; a control inside the prose must
    not silently reverse a change to the book's structure instead.
    """
    window = MWEmptyProject
    model = window.mdlOutline
    item = scene(model, "Typed in", text="Original text.")
    window.mainEditor.setCurrentModelIndex(
        model.indexFromItem(item), newTab=True)
    editor = window.mainEditor.currentEditor()
    qApp.processEvents()

    try:
        assert not editor.undoButton.isEnabled()

        # A structure change must NOT light up the editor's buttons.
        other = scene(model, "Elsewhere")
        window.undoStack.push(RemoveOutlineItemsCommand(
            model, [model.indexFromItem(other)]))
        qApp.processEvents()

        assert not editor.undoButton.isEnabled()

        # Typing must.
        editor.txtRedacText.setFocus()
        editor.txtRedacText.insertPlainText(" gggggg")
        qApp.processEvents()

        assert editor.undoButton.isEnabled()
        assert not editor.redoButton.isEnabled()

        editor.undoButton.click()
        qApp.processEvents()

        assert editor.txtRedacText.toPlainText() == "Original text."
        assert editor.redoButton.isEnabled()

        editor.redoButton.click()
        qApp.processEvents()

        assert "gggggg" in editor.txtRedacText.toPlainText()
    finally:
        window.undoStack.clear()
        window.mainEditor.closeAllTabs()


def test_undo_buttons_sit_left_of_the_view_controls(MWEmptyProject):
    window = MWEmptyProject
    model = window.mdlOutline
    item = scene(model, "Placed")
    window.mainEditor.setCurrentModelIndex(
        model.indexFromItem(item), newTab=True)
    editor = window.mainEditor.currentEditor()

    try:
        editor.resize(800, 400)
        assert editor.undoButton.x() < editor.redoButton.x()
        assert editor.redoButton.geometry().right() < (
            editor.markdownModeButton.x())
        # Inside the reserved strip, so no overlap with the text.
        top = editor.verticalLayout_2.getContentsMargins()[1]
        assert editor.undoButton.geometry().bottom() <= top
    finally:
        window.mainEditor.closeAllTabs()
