from PyQt5.QtCore import QModelIndex, QSortFilterProxyModel, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QStandardItem

from manuskript.functions import toInt
from manuskript.ui import style


class ImportanceCategoryProxyModel(QSortFilterProxyModel):
    """Flat proxy that groups source rows by their importance."""

    category_names = ("Main", "Secondary", "Minors")

    def __init__(self, importance_column, parent=None):
        super().__init__(parent)
        self._importance_column = int(importance_column)
        self._categories = [
            QStandardItem(self.tr(name))
            for name in self.category_names
        ]
        self._row_map = []

    def setSourceModel(self, model):
        old_model = self.sourceModel()
        if old_model is not None:
            for signal, slot in (
                (old_model.dataChanged, self._remap_if_importance_changed),
                (old_model.rowsInserted, self.rebuild),
                (old_model.rowsRemoved, self.rebuild),
                (old_model.rowsMoved, self.rebuild),
                (old_model.modelReset, self.rebuild),
            ):
                try:
                    signal.disconnect(slot)
                except TypeError:
                    pass

        super().setSourceModel(model)
        if model is not None:
            model.dataChanged.connect(self._remap_if_importance_changed)
            model.rowsInserted.connect(self.rebuild)
            model.rowsRemoved.connect(self.rebuild)
            model.rowsMoved.connect(self.rebuild)
            model.modelReset.connect(self.rebuild)
        self.rebuild()

    def _remap_if_importance_changed(self, top_left, bottom_right):
        if (
            top_left.column()
            <= self._importance_column
            <= bottom_right.column()
        ):
            self.rebuild()

    def rebuild(self, *args):
        self.beginResetModel()
        self._row_map = []
        source = self.sourceModel()
        if source is not None:
            for category, category_item in enumerate(self._categories):
                self._row_map.append(category_item)
                for row in range(source.rowCount(QModelIndex())):
                    importance = source.data(
                        source.index(
                            row,
                            self._importance_column,
                            QModelIndex(),
                        ),
                        Qt.DisplayRole,
                    )
                    if 2 - toInt(importance) == category:
                        self._row_map.append(row)
        self.endResetModel()

    def mapFromSource(self, source_index):
        if (
            not source_index.isValid()
            or source_index.parent().isValid()
        ):
            return QModelIndex()
        try:
            proxy_row = self._row_map.index(source_index.row())
        except ValueError:
            return QModelIndex()
        return self.createIndex(proxy_row, source_index.column())

    def mapToSource(self, proxy_index):
        if (
            not proxy_index.isValid()
            or proxy_index.parent().isValid()
            or proxy_index.row() >= len(self._row_map)
        ):
            return QModelIndex()
        source_row = self._row_map[proxy_index.row()]
        if not isinstance(source_row, int):
            return QModelIndex()
        source = self.sourceModel()
        if source is None:
            return QModelIndex()
        return source.index(
            source_row,
            proxy_index.column(),
            QModelIndex(),
        )

    def index(self, row, column, parent=QModelIndex()):
        if (
            parent.isValid()
            or row < 0
            or row >= len(self._row_map)
            or column < 0
            or column >= self.columnCount()
        ):
            return QModelIndex()
        return self.createIndex(row, column)

    def parent(self, index=QModelIndex()):
        return QModelIndex()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._row_map)

    def columnCount(self, parent=QModelIndex()):
        source = self.sourceModel()
        if parent.isValid() or source is None:
            return 0
        return source.columnCount(QModelIndex())

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        source_index = self.mapToSource(index)
        if source_index.isValid():
            return self.sourceModel().data(source_index, role)

        category = self._row_map[index.row()]
        if role == Qt.DisplayRole:
            return category.text()
        if role == Qt.ForegroundRole:
            return QBrush(QColor(style.highlightedTextDark))
        if role == Qt.BackgroundRole:
            return QBrush(QColor(style.highlightLight))
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        if role == Qt.FontRole:
            font = QFont()
            font.setWeight(QFont.Bold)
            return font
        return None

    def flags(self, index):
        if not self.mapToSource(index).isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def item(self, row, column, parent=QModelIndex()):
        source_index = self.mapToSource(
            self.index(row, column, parent)
        )
        if not source_index.isValid():
            return None
        source = self.sourceModel()
        if hasattr(source, "itemFromIndex"):
            return source.itemFromIndex(source_index)
        return source_index.internalPointer()
