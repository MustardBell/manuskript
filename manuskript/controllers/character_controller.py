from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import QWidget

from manuskript.functions import iconColor
from manuskript.ui.bulkInfoManager import Ui_BulkInfoManager


class CharacterController:
    """Coordinate character models, widgets, and character-specific dialogs.

    Takes the panel it drives, the models it edits, and the two services
    every panel needs, rather than a window that can answer anything.
    """

    def __init__(self, models, panel, navigation, dialogs):
        self.models = models
        self.panel = panel
        self.navigation = navigation
        self.dialogs = dialogs
        self.bulk_ui = None
        self.bulk_affected_characters = []
        self._tabs = []

    def capture_tabs(self):
        tabs = self.panel.tabs
        self._tabs = [
            {
                "widget": tabs.widget(index),
                "title": tabs.tabText(index),
            }
            for index in range(tabs.count())
        ]

    def restore_tabs(self):
        for tab in self._tabs:
            self.panel.tabs.addTab(tab["widget"], tab["title"])

    def reset(self):
        """Release temporary character UI state between projects."""
        self.set_bulk_mode(False)

    def record_current_selection(self):
        characters = self._selected_characters()
        self.navigation.record(
            ("character", characters[0].ID() if characters else None),
            selection_empty=not characters,
        )

    def handle_selection_changed(self):
        selected_characters = self._selected_characters()
        if not selected_characters:
            self.navigation.record(
                ("character", None),
                selection_empty=True,
            )
            self.panel.tabs.setEnabled(False)
            return

        character = selected_characters[0]
        self.change_current_character(character)
        self.navigation.record(
            ("character", character.ID()),
            selection_empty=False,
        )

        if len(selected_characters) > 1:
            self.set_bulk_mode(True)
        else:
            if self.bulk_ui is not None:
                self.bulk_ui.lblCharactersDynamic.setText(
                    self.character_selection_text()
                )
                table_model = self.bulk_ui.tableView.model()
                if table_model.rowCount() > 0:
                    if not self.dialogs.confirm(
                        "Un-applied data!",
                        "There are un-applied entries in this tab. "
                        "Discard them?",
                        default_no=True,
                    ):
                        return
            self.set_bulk_mode(False)
        self.panel.tabs.setEnabled(True)

    def _selected_characters(self):
        return list(
            filter(None, self.panel.characters.currentCharacters())
        )

    def set_bulk_mode(self, enabled):
        if enabled and self.bulk_ui is None:
            bulk_widget = QWidget()
            bulk_ui = Ui_BulkInfoManager()
            bulk_ui.setupUi(bulk_widget)
            self.bulk_ui = bulk_ui

            model = QStandardItemModel()
            model.setColumnCount(2)
            model.setHorizontalHeaderLabels([
                self.dialogs.translate("Name"),
                self.dialogs.translate("Value"),
            ])
            self.configure_info_view(bulk_ui.tableView)
            bulk_ui.tableView.setModel(model)

            self.panel.tabs.clear()
            self.panel.tabs.addTab(
                bulk_widget,
                self.dialogs.translate("Bulk Info Manager"),
            )
            bulk_ui.lblCharactersDynamic.setText(
                self.character_selection_text()
            )
            self._connect_bulk_actions(bulk_ui)
        elif enabled:
            self.bulk_ui.lblCharactersDynamic.setText(
                self.character_selection_text()
            )
        elif self.bulk_ui is not None:
            self.panel.tabs.clear()
            self.restore_tabs()
            self.bulk_ui = None
            self.bulk_affected_characters.clear()

    def refresh_bulk_affected_characters(self):
        self.bulk_affected_characters = [
            character.name()
            for character in self.panel.characters.currentCharacters()
            if character is not None
        ]

    def character_selection_text(self):
        self.refresh_bulk_affected_characters()
        return ", ".join(
            '"{}"'.format(name) for name in self.bulk_affected_characters
        )

    def _connect_bulk_actions(self, bulk_ui):
        bulk_ui.btnPersoBulkAddInfo.clicked.connect(
            lambda: self.add_bulk_info(bulk_ui)
        )
        bulk_ui.btnPersoBulkRmInfo.clicked.connect(
            lambda: self.remove_bulk_info(bulk_ui)
        )
        bulk_ui.btnPersoBulkApply.clicked.connect(
            lambda: self.apply_bulk_info(bulk_ui)
        )

    def apply_bulk_info(self, bulk_ui):
        model = bulk_ui.tableView.model()
        if model.rowCount() == 0:
            self.dialogs.warn(
                "No Entries!",
                "Please add entries to apply to the selected characters.",
            )
            return

        for character_id in self.panel.characters.currentCharacterIDs():
            for row in range(model.rowCount()):
                self.models.characters.addCharacterInfo(
                    character_id,
                    model.item(row, 0).text(),
                    model.item(row, 1).text(),
                )

        self.dialogs.inform(
            "Bulk Info Applied",
            "The bulk info has been applied to the selected characters.",
        )
        model.removeRows(0, model.rowCount())

    def add_bulk_info(self, bulk_ui):
        entry = self.dialogs.ask_name_and_value()
        if entry is None:
            return
        description, value = entry
        bulk_ui.tableView.model().appendRow([
            QStandardItem(description),
            QStandardItem(value),
        ])
        bulk_ui.tableView.update()

    def remove_bulk_info(self, bulk_ui):
        selected_rows = bulk_ui.tableView.selectionModel().selectedRows()
        for index in reversed(selected_rows):
            bulk_ui.tableView.model().removeRow(index.row())

    def add_character_info(self):
        character_id = self.panel.characters.currentCharacterID()
        if character_id is None:
            return

        entry = self.dialogs.ask_name_and_value()
        if entry is None:
            return
        description, value = entry
        self.models.characters.addCharacterInfo(
            character_id,
            description,
            value,
        )

    def remove_character_info(self):
        character_id = self.panel.characters.currentCharacterID()
        if character_id is None:
            return
        rows = {
            index.row()
            for index in self.panel.info.selectedIndexes()
        }
        self.models.characters.removeCharacterInfo(character_id, rows)

    def choose_character_color(self):
        character_id = self.panel.characters.currentCharacterID()
        character = self.models.characters.getCharacterByID(character_id)
        if character is None:
            return

        color = self.dialogs.choose_color(iconColor(character.icon))
        if color is not None:
            character.setColor(color)
            self.update_character_color(character_id)

    def change_character_pov_state(self, state):
        character_id = self.panel.characters.currentCharacterID()
        character = self.models.characters.getCharacterByID(character_id)
        if character is None:
            return
        character.setPOVEnabled(state == Qt.Checked)
        self.update_character_pov_state(character_id)

    def change_current_character(self, character):
        if character is None:
            return

        index = character.index()
        for widget in self.panel.fields:
            widget.setCurrentModelIndex(index)

        self.update_character_color(character.ID())
        self.update_character_importance(character.ID())
        self.update_character_pov_state(character.ID())
        self.panel.info.setRootIndex(index)
        if self.models.characters.rowCount(index):
            self.configure_info_view(self.panel.info)

    def configure_info_view(self, info_view):
        info_view.horizontalHeader().setStretchLastSection(True)
        info_view.horizontalHeader().setMinimumSectionSize(20)
        info_view.horizontalHeader().setMaximumSectionSize(500)
        info_view.verticalHeader().hide()

    def update_character_color(self, character_id):
        character = self.models.characters.getCharacterByID(character_id)
        if character is not None:
            self.panel.color_button.setStyleSheet(
                "background:{};".format(character.color().name())
            )

    def update_character_importance(self, character_id):
        character = self.models.characters.getCharacterByID(character_id)
        if character is not None:
            self.panel.importance_slider.setValue(
                int(character.importance())
            )

    def update_character_pov_state(self, character_id):
        character = self.models.characters.getCharacterByID(character_id)
        if character is None:
            return

        blocker = QSignalBlocker(self.panel.pov_checkbox)
        state = Qt.Checked if character.pov() else Qt.Unchecked
        self.panel.pov_checkbox.setCheckState(state)
        del blocker
        self.panel.pov_checkbox.setEnabled(
            len(self.models.outline.findItemsByPOV(character_id)) == 0
        )

    def delete_characters(self):
        character_ids = self.panel.characters.currentCharacterIDs()
        if not character_ids:
            return []

        if not self.dialogs.confirm(
            "Delete selected character(s)?",
            "Are you sure you want to delete the selected character(s)?",
        ):
            return []

        for character_id in character_ids:
            outline_ids = self.models.outline.findItemsByPOV(character_id)
            self.models.characters.removeCharacter(character_id)
            for outline_id in outline_ids:
                item = self.models.outline.getItemByID(outline_id)
                if item is not None:
                    item.resetPOV()
        return character_ids
