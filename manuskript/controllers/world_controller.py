from functools import partial

from PyQt5.QtCore import QModelIndex
from PyQt5.QtWidgets import QAction, QMenu


class WorldController:
    """Coordinate world-building hierarchy data with its persistent widgets.

    Takes the panel it drives, the model it edits, and the two services
    every panel needs, rather than a window that can answer anything.
    """

    def __init__(self, models, panel, navigation, dialogs):
        self.models = models
        self.panel = panel
        self.navigation = navigation
        self.dialogs = dialogs
        self._data_set_menu = None

    def reset(self):
        """Release menu actions that target the current project model."""
        self.panel.data_set_button.setMenu(None)
        if self._data_set_menu is not None:
            self._data_set_menu.deleteLater()
            self._data_set_menu = None

    def current_index(self):
        if self.panel.tree.selectedIndexes():
            return self.panel.tree.currentIndex()
        return QModelIndex()

    def record_current_selection(self):
        index = self.current_index()
        world_id = (
            self.models.world.ID(index)
            if index.isValid()
            else None
        )
        self.navigation.record(
            ("world", world_id),
            selection_empty=not index.isValid(),
        )

    def handle_selection_changed(self, *_):
        index = self.current_index()
        if not index.isValid():
            self._clear_current_item()
            self.navigation.record(
                ("world", None),
                selection_empty=True,
            )
            return

        self.navigation.record(
            ("world", self.models.world.ID(index)),
            selection_empty=False,
        )
        self.panel.tabs.setEnabled(True)
        for widget in self.panel.fields:
            widget.setCurrentModelIndex(index)

    def _clear_current_item(self):
        self.panel.tabs.setEnabled(False)
        invalid = QModelIndex()
        for widget in self.panel.fields:
            widget.setCurrentModelIndex(invalid)

    def add_item(self, _checked=False, title=None, parent=None):
        model = self.models.world
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
            self.panel.tree.setExpanded(parent_index, True)
        self.panel.tree.setCurrentIndex(model.indexFromItem(item))
        return item

    def remove_selected_items(self, _checked=False):
        return self.models.world.removeItems(
            self.panel.tree.selectedIndexes()
        )

    def build_data_set_menu(self):
        menu = QMenu(self.dialogs.parent)
        for name in self.models.world.dataSets():
            action = QAction(name, menu)
            action.triggered.connect(
                partial(self.populate_data_set, name)
            )
            menu.addAction(action)

        old_menu = self._data_set_menu
        self._data_set_menu = menu
        self.panel.data_set_button.setMenu(menu)
        if old_menu is not None:
            old_menu.deleteLater()
        return menu

    def populate_data_set(self, name, _checked=False):
        added_items = self.models.world.populateDataSet(name)
        if added_items:
            self.panel.tree.expandAll()
        return added_items

    def select_by_id(self, world_id):
        index = self.models.world.indexByID(world_id)
        if not index.isValid():
            return False
        self.panel.tree.setCurrentIndex(index)
        return True
