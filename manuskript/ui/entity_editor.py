"""Window-local editor for one generic entity document."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)


class EntityEditorDialog(QDialog):
    """Edit generic entity fields without knowing any story semantics."""

    def __init__(self, entity, schemas, save_entity, parent=None):
        super().__init__(parent)
        self.entity = entity
        self._saveEntity = save_entity
        self.setObjectName("entityEditorDialog")
        self.setWindowTitle(self.tr("Entity — {}").format(entity.title))
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(560, 480)

        self.titleEdit = QLineEdit(entity.title, self)
        self.titleEdit.setObjectName("entityTitleEdit")
        self.titleEdit.setAccessibleName(self.tr("Entity title"))
        self.typeCombo = QComboBox(self)
        self.typeCombo.setObjectName("entityTypeCombo")
        self.typeCombo.setEditable(True)
        for schema in schemas:
            self.typeCombo.addItem(schema.label, schema.type)
        type_index = self.typeCombo.findData(entity.type)
        if type_index < 0:
            self.typeCombo.addItem(entity.type, entity.type)
            type_index = self.typeCombo.count() - 1
        self.typeCombo.setCurrentIndex(type_index)

        self.aliasesEdit = QPlainTextEdit(self)
        self.aliasesEdit.setObjectName("entityAliasesEdit")
        self.aliasesEdit.setAccessibleName(
            self.tr("Aliases, one per line")
        )
        self.aliasesEdit.setPlainText("\n".join(entity.aliases))
        self.aliasesEdit.setMaximumHeight(120)
        self.pathLabel = QLabel(entity.document.source_path, self)
        self.pathLabel.setObjectName("entityPathLabel")
        self.pathLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.pathLabel.setWordWrap(True)

        form = QFormLayout()
        form.addRow(self.tr("&Title:"), self.titleEdit)
        form.addRow(self.tr("T&ype:"), self.typeCombo)
        form.addRow(self.tr("&Aliases:"), self.aliasesEdit)
        form.addRow(self.tr("File:"), self.pathLabel)

        body_label = QLabel(self.tr("&Markdown document:"), self)
        self.bodyEdit = QPlainTextEdit(self)
        self.bodyEdit.setObjectName("entityBodyEdit")
        self.bodyEdit.setAccessibleName(self.tr("Entity Markdown document"))
        self.bodyEdit.setPlainText(entity.document.text)
        body_label.setBuddy(self.bodyEdit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.buttons.button(QDialogButtonBox.Save).setDefault(True)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(body_label)
        layout.addWidget(self.bodyEdit, 1)
        layout.addWidget(self.buttons)

    def save(self):
        typed_type = self.typeCombo.currentText().strip()
        known_index = self.typeCombo.findText(typed_type, Qt.MatchFixedString)
        entity_type = (
            self.typeCombo.itemData(known_index)
            if known_index >= 0
            else typed_type
        )
        aliases = tuple(
            line.strip() for line in self.aliasesEdit.toPlainText().splitlines()
            if line.strip()
        )
        try:
            self._saveEntity(
                self.entity.id,
                title=self.titleEdit.text(),
                entity_type=str(entity_type),
                aliases=aliases,
                text=self.bodyEdit.toPlainText(),
            )
        except (KeyError, PermissionError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.tr("Cannot save entity"),
                str(error),
            )
            return
        self.accept()


class EntityEditorController:
    """Own non-modal child dialogs for one workspace window."""

    def __init__(self, parent, catalog, update_entity):
        self.parent = parent
        self.catalog = catalog
        self.updateEntity = update_entity
        self._dialogs = {}

    def open(self, entity_id):
        entity = self.catalog.find(entity_id)
        if entity is None or entity not in self.catalog.native_entities:
            return False
        existing = self._dialogs.get(entity_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return True
        dialog = EntityEditorDialog(
            entity,
            self.catalog.schemas.schemas,
            self.updateEntity,
            self.parent,
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._dialogs[entity_id] = dialog
        dialog.destroyed.connect(
            lambda _object=None, key=entity_id, dialogs=self._dialogs:
                dialogs.pop(key, None)
        )
        dialog.show()
        return True
