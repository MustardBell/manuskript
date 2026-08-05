"""Reversible outline structure edits.

Deleting part of a manuscript used to be final: the model dropped the rows and
the only recovery was a project revision. These commands keep the removed
items alive on an undo stack so the structure of a book is as recoverable as
the text inside it.
"""

from PyQt5.QtCore import QCoreApplication, QModelIndex
from PyQt5.QtWidgets import QUndoCommand


class RemoveOutlineItemsCommand(QUndoCommand):
    """Remove outline items, putting them back where they were on undo.

    Removals are planned before anything is touched, because a QModelIndex
    does not survive the row it points at. Each entry records the parent item
    and row, which stay meaningful across the operation, and undo replays them
    in reverse so a folder is restored before the children that lived in it.
    """

    def __init__(self, model, indexes, parent=None):
        super().__init__(parent)
        self._model = model
        self._plan = self._build_plan(model, indexes)
        self.setText(self._describe(model))

    @property
    def count(self):
        return len(self._plan)

    def isEmpty(self):
        return not self._plan

    def redo(self):
        for parent_item, row, _item in self._plan:
            self._model.removeRows(row, 1, self._index_of(parent_item))

    def undo(self):
        # Reverse order so a parent exists again before its children return.
        for parent_item, row, item in reversed(self._plan):
            self._model.insertItems(
                [item], row, self._index_of(parent_item))

    # ------------------------------------------------------------------

    @staticmethod
    def _build_plan(model, indexes):
        """Deepest first, then bottom row first, matching removeIndexes.

        Removing a lower row first keeps the rows above it valid, and
        removing children before their parent keeps the parent addressable.
        """
        entries = []
        for index in indexes:
            item = index.internalPointer()
            if item is None:
                continue
            entries.append((item.level(), index.row(), item))
        entries.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
        return [
            (item.parent(), row, item)
            for _level, row, item in entries
        ]

    def _index_of(self, parent_item):
        if parent_item is None or parent_item is self._model.rootItem:
            return QModelIndex()
        return parent_item.index()

    def _describe(self, model):
        # QUndoCommand is not a QObject, so there is no self.tr here.
        translate = QCoreApplication.translate
        if len(self._plan) == 1:
            return translate(
                "RemoveOutlineItemsCommand", 'Delete "{}"'
            ).format(self._plan[0][2].title())
        return translate(
            "RemoveOutlineItemsCommand", "Delete {} items"
        ).format(len(self._plan))
