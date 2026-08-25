"""Workspace-local outline selection independent of any one tree view."""

from PyQt5.QtCore import QItemSelectionModel, QModelIndex, QObject


class WorkspaceOutlineSelection(QObject):
    """Own the document selection shared by this workspace's views.

    Project Tree is one optional presentation of this state, not its owner.
    Editor can therefore keep selecting and opening documents in a tool-free
    workspace, while a complete primary binds its tree to the same native Qt
    selection model.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selection = None

    def bind_project_model(self, model):
        self.unbind_project_model()
        self._selection = QItemSelectionModel(model, self)
        return self._selection

    def unbind_project_model(self):
        selection = self._selection
        self._selection = None
        if selection is not None:
            selection.deleteLater()

    def selectionModel(self):
        return self._selection

    def currentIndex(self):
        return (
            self._selection.currentIndex()
            if self._selection is not None else QModelIndex()
        )

    def selectedIndexes(self):
        return (
            self._selection.selectedIndexes()
            if self._selection is not None else []
        )

    def setCurrentIndex(self, index):
        if self._selection is None:
            return
        self._selection.setCurrentIndex(
            index,
            QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows,
        )

    def dispose(self):
        self.unbind_project_model()
