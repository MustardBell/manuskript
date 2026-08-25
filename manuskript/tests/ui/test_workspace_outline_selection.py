from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.ui.workspace_outline_selection import (
    WorkspaceOutlineSelection,
)


def test_workspace_selection_exists_without_a_project_tree_widget():
    model = QStandardItemModel()
    model.appendRow(QStandardItem("Scene"))
    index = model.index(0, 0)
    selection = WorkspaceOutlineSelection()

    selection.bind_project_model(model)
    selection.setCurrentIndex(index)

    assert selection.currentIndex() == index
    assert index in selection.selectedIndexes()


def test_rebinding_replaces_project_specific_selection_state():
    first = QStandardItemModel()
    first.appendRow(QStandardItem("First"))
    second = QStandardItemModel()
    second.appendRow(QStandardItem("Second"))
    selection = WorkspaceOutlineSelection()
    selection.bind_project_model(first)
    selection.setCurrentIndex(first.index(0, 0))

    replacement = selection.bind_project_model(second)

    assert selection.selectionModel() is replacement
    assert not selection.currentIndex().isValid()
    assert selection.selectedIndexes() == []


def test_primary_project_tree_presents_the_workspace_owned_selection(
        MWEmptyProject):
    window = MWEmptyProject

    assert (
        window.corePanels.project_tree.tree.selectionModel()
        is window.outlineSelection.selectionModel()
    )
