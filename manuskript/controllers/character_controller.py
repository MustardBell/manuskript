from PyQt5.QtCore import Qt, QSignalBlocker
from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import (
    QColorDialog,
    QDialog,
    QMessageBox,
    QWidget,
)

from manuskript.functions import iconColor
from manuskript.ui import characterInfoDialog
from manuskript.ui.bulkInfoManager import Ui_BulkInfoManager


class CharacterController:
    """Coordinate character models, widgets, and character-specific dialogs."""

    def __init__(self, window):
        self.window = window
        self.bulk_ui = None
        self.bulk_affected_characters = []
        self._tabs = []

    def capture_tabs(self):
        self._tabs = [
            {
                "widget": self.window.tabPersos.widget(index),
                "title": self.window.tabPersos.tabText(index),
            }
            for index in range(self.window.tabPersos.count())
        ]

    def restore_tabs(self):
        for tab in self._tabs:
            self.window.tabPersos.addTab(tab["widget"], tab["title"])

    def reset(self):
        """Release temporary character UI state between projects."""
        self.set_bulk_mode(False)

    def record_current_selection(self):
        characters = list(filter(None, self.window.lstCharacters.currentCharacters()))
        if not characters:
            self.window.pushHistory(("character", None))
            self.window._previousSelectionEmpty = True
            return
        self.window.pushHistory(("character", characters[0].ID()))
        self.window._previousSelectionEmpty = False

    def handle_selection_changed(self):
        selected_characters = list(
            filter(None, self.window.lstCharacters.currentCharacters())
        )
        if not selected_characters:
            self.window.pushHistory(("character", None))
            self.window.tabPersos.setEnabled(False)
            self.window._previousSelectionEmpty = True
            return

        character = selected_characters[0]
        self.change_current_character(character)
        self.window.pushHistory(("character", character.ID()))
        self.window._previousSelectionEmpty = False

        if len(selected_characters) > 1:
            self.set_bulk_mode(True)
        else:
            if self.bulk_ui is not None:
                self.bulk_ui.lblCharactersDynamic.setText(
                    self.character_selection_text()
                )
                table_model = self.bulk_ui.tableView.model()
                if table_model.rowCount() > 0:
                    confirm = QMessageBox.warning(
                        self.window,
                        self.window.tr("Un-applied data!"),
                        self.window.tr(
                            "There are un-applied entries in this tab. "
                            "Discard them?"
                        ),
                        QMessageBox.Yes | QMessageBox.No,
                        defaultButton=QMessageBox.No,
                    )
                    if confirm != QMessageBox.Yes:
                        return
            self.set_bulk_mode(False)
        self.window.tabPersos.setEnabled(True)

    def set_bulk_mode(self, enabled):
        if enabled and self.bulk_ui is None:
            bulk_widget = QWidget()
            bulk_ui = Ui_BulkInfoManager()
            bulk_ui.setupUi(bulk_widget)
            self.bulk_ui = bulk_ui

            model = QStandardItemModel()
            model.setColumnCount(2)
            model.setHorizontalHeaderLabels(
                [self.window.tr("Name"), self.window.tr("Value")]
            )
            self.configure_info_view(bulk_ui.tableView)
            bulk_ui.tableView.setModel(model)

            self.window.tabPersos.clear()
            self.window.tabPersos.addTab(
                bulk_widget, self.window.tr("Bulk Info Manager")
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
            self.window.tabPersos.clear()
            self.restore_tabs()
            self.bulk_ui = None
            self.bulk_affected_characters.clear()

    def refresh_bulk_affected_characters(self):
        self.bulk_affected_characters = [
            character.name()
            for character in self.window.lstCharacters.currentCharacters()
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
            QMessageBox.warning(
                self.window,
                self.window.tr("No Entries!"),
                self.window.tr(
                    "Please add entries to apply to the selected characters."
                ),
            )
            return

        for character_id in self.window.lstCharacters.currentCharacterIDs():
            for row in range(model.rowCount()):
                self.window.mdlCharacter.addCharacterInfo(
                    character_id,
                    model.item(row, 0).text(),
                    model.item(row, 1).text(),
                )

        QMessageBox.information(
            self.window,
            self.window.tr("Bulk Info Applied"),
            self.window.tr(
                "The bulk info has been applied to the selected characters."
            ),
        )
        model.removeRows(0, model.rowCount())

    def add_bulk_info(self, bulk_ui):
        dialog = QDialog(self.window)
        dialog_ui = characterInfoDialog.Ui_characterInfoDialog()
        dialog_ui.setupUi(dialog)

        if dialog.exec_() == QDialog.Accepted:
            bulk_ui.tableView.model().appendRow([
                QStandardItem(dialog_ui.descriptionLineEdit.text()),
                QStandardItem(dialog_ui.valueLineEdit.text()),
            ])
            bulk_ui.tableView.update()

    def remove_bulk_info(self, bulk_ui):
        selected_rows = bulk_ui.tableView.selectionModel().selectedRows()
        for index in reversed(selected_rows):
            bulk_ui.tableView.model().removeRow(index.row())

    def add_character_info(self):
        character_id = self.window.lstCharacters.currentCharacterID()
        if character_id is None:
            return

        dialog = QDialog(self.window)
        dialog_ui = characterInfoDialog.Ui_characterInfoDialog()
        dialog_ui.setupUi(dialog)
        if dialog.exec_() == QDialog.Accepted:
            self.window.mdlCharacter.addCharacterInfo(
                character_id,
                dialog_ui.descriptionLineEdit.text(),
                dialog_ui.valueLineEdit.text(),
            )

    def remove_character_info(self):
        character_id = self.window.lstCharacters.currentCharacterID()
        if character_id is None:
            return
        rows = {
            index.row()
            for index in self.window.tblPersoInfos.selectedIndexes()
        }
        self.window.mdlCharacter.removeCharacterInfo(character_id, rows)

    def choose_character_color(self):
        character_id = self.window.lstCharacters.currentCharacterID()
        character = self.window.mdlCharacter.getCharacterByID(character_id)
        if character is None:
            return

        color = iconColor(character.icon)
        color = QColorDialog.getColor(color, self.window)
        if color.isValid():
            character.setColor(color)
            self.update_character_color(character_id)

    def change_character_pov_state(self, state):
        character_id = self.window.lstCharacters.currentCharacterID()
        character = self.window.mdlCharacter.getCharacterByID(character_id)
        if character is None:
            return
        character.setPOVEnabled(state == Qt.Checked)
        self.update_character_pov_state(character_id)

    def change_current_character(self, character):
        if character is None:
            return

        index = character.index()
        for widget in [
            self.window.txtPersoName,
            self.window.sldPersoImportance,
            self.window.txtPersoMotivation,
            self.window.txtPersoGoal,
            self.window.txtPersoConflict,
            self.window.txtPersoEpiphany,
            self.window.txtPersoSummarySentence,
            self.window.txtPersoSummaryPara,
            self.window.txtPersoSummaryFull,
            self.window.txtPersoNotes,
        ]:
            widget.setCurrentModelIndex(index)

        self.update_character_color(character.ID())
        self.update_character_importance(character.ID())
        self.update_character_pov_state(character.ID())
        self.window.tblPersoInfos.setRootIndex(index)
        if self.window.mdlCharacter.rowCount(index):
            self.configure_info_view(self.window.tblPersoInfos)

    def configure_info_view(self, info_view):
        info_view.horizontalHeader().setStretchLastSection(True)
        info_view.horizontalHeader().setMinimumSectionSize(20)
        info_view.horizontalHeader().setMaximumSectionSize(500)
        info_view.verticalHeader().hide()

    def update_character_color(self, character_id):
        character = self.window.mdlCharacter.getCharacterByID(character_id)
        if character is not None:
            self.window.btnPersoColor.setStyleSheet(
                "background:{};".format(character.color().name())
            )

    def update_character_importance(self, character_id):
        character = self.window.mdlCharacter.getCharacterByID(character_id)
        if character is not None:
            self.window.sldPersoImportance.setValue(
                int(character.importance())
            )

    def update_character_pov_state(self, character_id):
        character = self.window.mdlCharacter.getCharacterByID(character_id)
        if character is None:
            return

        blocker = QSignalBlocker(self.window.chkPersoPOV)
        state = Qt.Checked if character.pov() else Qt.Unchecked
        self.window.chkPersoPOV.setCheckState(state)
        del blocker
        self.window.chkPersoPOV.setEnabled(
            len(self.window.mdlOutline.findItemsByPOV(character_id)) == 0
        )

    def delete_characters(self):
        character_ids = self.window.lstCharacters.currentCharacterIDs()
        if not character_ids:
            return []

        confirm = QMessageBox.warning(
            self.window,
            self.window.tr("Delete selected character(s)?"),
            self.window.tr(
                "Are you sure you want to delete the selected character(s)?"
            ),
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return []

        for character_id in character_ids:
            outline_ids = self.window.mdlOutline.findItemsByPOV(character_id)
            self.window.mdlCharacter.removeCharacter(character_id)
            for outline_id in outline_ids:
                item = self.window.mdlOutline.getItemByID(outline_id)
                if item is not None:
                    item.resetPOV()
        return character_ids
