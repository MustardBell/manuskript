from functools import partial

from PyQt5.QtCore import QModelIndex
from PyQt5.QtWidgets import QAction, QMenu


class WorldController:
    """Coordinate world-building hierarchy data with its persistent widgets."""

    def __init__(self, window):
        self.window = window
        self._data_set_menu = None

    def reset(self):
        """Release menu actions that target the current project model."""
        self.window.btnWorldEmptyData.setMenu(None)
        if self._data_set_menu is not None:
            self._data_set_menu.deleteLater()
            self._data_set_menu = None

    def current_index(self):
        if self.window.treeWorld.selectedIndexes():
            return self.window.treeWorld.currentIndex()
        return QModelIndex()

    def record_current_selection(self):
        index = self.current_index()
        world_id = (
            self.window.mdlWorld.ID(index)
            if index.isValid()
            else None
        )
        self.window.pushHistory(("world", world_id))
        self.window._previousSelectionEmpty = not index.isValid()

    def handle_selection_changed(self, *_):
        index = self.current_index()
        if not index.isValid():
            self._clear_current_item()
            self.window.pushHistory(("world", None))
            self.window._previousSelectionEmpty = True
            return

        self.window.pushHistory(
            ("world", self.window.mdlWorld.ID(index))
        )
        self.window._previousSelectionEmpty = False
        self.window.tabWorld.setEnabled(True)
        for widget in [
            self.window.txtWorldName,
            self.window.txtWorldDescription,
            self.window.txtWorldPassion,
            self.window.txtWorldConflict,
        ]:
            widget.setCurrentModelIndex(index)

    def _clear_current_item(self):
        self.window.tabWorld.setEnabled(False)
        invalid = QModelIndex()
        for widget in [
            self.window.txtWorldName,
            self.window.txtWorldDescription,
            self.window.txtWorldPassion,
            self.window.txtWorldConflict,
        ]:
            widget.setCurrentModelIndex(invalid)

    def add_item(self, _checked=False, title=None, parent=None):
        model = self.window.mdlWorld
        parent_item = parent
        parent_index = QModelIndex()
        if parent_item is None:
            parent_index = self.current_index()
            parent_item = model.itemFromIndex(parent_index)
        if parent_item is None:
            parent_item = model.invisibleRootItem()
        elif not parent_index.isValid():
            parent_index = model.indexFromItem(parent_item)

        item = model.addItem(title=title, parent=parent_item)
        if parent_index.isValid():
            self.window.treeWorld.setExpanded(parent_index, True)
        self.window.treeWorld.setCurrentIndex(model.indexFromItem(item))
        return item

    def remove_selected_items(self, _checked=False):
        return self.window.mdlWorld.removeItems(
            self.window.treeWorld.selectedIndexes()
        )

    def build_data_set_menu(self):
        menu = QMenu(self.window)
        for name in self.window.mdlWorld.dataSets():
            action = QAction(name, menu)
            action.triggered.connect(
                partial(self.populate_data_set, name)
            )
            menu.addAction(action)

        old_menu = self._data_set_menu
        self._data_set_menu = menu
        self.window.btnWorldEmptyData.setMenu(menu)
        if old_menu is not None:
            old_menu.deleteLater()
        return menu

    def populate_data_set(self, name, _checked=False):
        added_items = self.window.mdlWorld.populateDataSet(name)
        if added_items:
            self.window.treeWorld.expandAll()
        return added_items

    def select_by_id(self, world_id):
        index = self.window.mdlWorld.indexByID(world_id)
        if not index.isValid():
            return False
        self.window.treeWorld.setCurrentIndex(index)
        return True
