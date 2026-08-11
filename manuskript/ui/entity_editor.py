"""Window-local editor for one canonical entity document."""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from manuskript.domain.canonical_project import StructuredMetadataField
from manuskript.domain.morphology import MorphologyProfile
from manuskript.ui.morphology_editor import MorphologyParadigmDialog


class EntityEditorDialog(QDialog):
    """Edit generic entity fields without knowing any story semantics."""

    def __init__(
        self,
        entity,
        schemas,
        save_entity,
        parent=None,
        morphology_providers=None,
        read_only=False,
    ):
        super().__init__(parent)
        self.entity = entity
        self._saveEntity = save_entity
        self._morphologyProviders = morphology_providers
        self._morphologyProfile = MorphologyProfile.from_entity(entity)
        self._morphologyChanged = False
        self._readOnly = bool(read_only)
        self.setObjectName("entityEditorDialog")
        schema = next(
            (item for item in schemas if item.type == entity.type), None
        )
        entity_label = schema.label if schema is not None else self.tr("Entity")
        self.setWindowTitle(
            self.tr("{} — {}").format(entity_label, entity.title)
        )
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(560, 540)

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
        self.morphologyButton = QPushButton(
            self.tr("Edit name &forms…"), self
        )
        self.morphologyButton.setObjectName("editMorphologyButton")
        self.morphologyButton.setAccessibleDescription(self.tr(
            "Review deterministic grammatical forms and author overrides."
        ))
        provider_available = (
            self._morphologyProfile is None
            or (
                morphology_providers is not None
                and morphology_providers.get(
                    self._morphologyProfile.provider_id
                ) is not None
            )
        )
        self.morphologyButton.setEnabled(
            not self._readOnly
            and
            morphology_providers is not None
            and bool(morphology_providers.providers)
            and provider_available
        )
        if not provider_available:
            self.morphologyButton.setToolTip(self.tr(
                "Install the configured morphology provider before editing "
                "this profile."
            ))
        self.morphologyButton.clicked.connect(self._editMorphology)
        self.morphologySummary = QLabel(self)
        self.morphologySummary.setObjectName("morphologySummary")
        self.morphologySummary.setWordWrap(True)
        self._updateMorphologySummary()

        form = QFormLayout()
        form.addRow(self.tr("&Title:"), self.titleEdit)
        form.addRow(self.tr("T&ype:"), self.typeCombo)
        form.addRow(self.tr("&Aliases:"), self.aliasesEdit)
        form.addRow(self.tr("File:"), self.pathLabel)
        form.addRow(self.tr("Name forms:"), self.morphologyButton)
        form.addRow("", self.morphologySummary)

        propertiesLabel = QLabel(self.tr("&Properties:"), self)
        self.propertiesTable = QTableWidget(0, 2, self)
        self.propertiesTable.setObjectName("entityPropertiesTable")
        self.propertiesTable.setAccessibleName(
            self.tr("Entity properties")
        )
        self.propertiesTable.setHorizontalHeaderLabels((
            self.tr("Property"), self.tr("Value")
        ))
        self.propertiesTable.horizontalHeader().setStretchLastSection(True)
        self.propertiesTable.verticalHeader().setVisible(False)
        propertiesLabel.setBuddy(self.propertiesTable)
        for field in entity.metadata:
            if field.name == "morphology":
                continue
            self._appendProperty(field.name, field.value)

        self.addPropertyButton = QPushButton(
            self.tr("Add &property"), self
        )
        self.addPropertyButton.setObjectName("addEntityPropertyButton")
        self.removePropertyButton = QPushButton(
            self.tr("&Remove property"), self
        )
        self.removePropertyButton.setObjectName(
            "removeEntityPropertyButton"
        )
        self.addPropertyButton.clicked.connect(
            lambda: self._appendProperty("", "")
        )
        self.removePropertyButton.clicked.connect(self._removeProperty)
        propertyButtons = QHBoxLayout()
        propertyButtons.addWidget(self.addPropertyButton)
        propertyButtons.addWidget(self.removePropertyButton)
        propertyButtons.addStretch(1)

        body_label = QLabel(self.tr("&Markdown document:"), self)
        self.bodyEdit = QPlainTextEdit(self)
        self.bodyEdit.setObjectName("entityBodyEdit")
        self.bodyEdit.setAccessibleName(self.tr("Entity Markdown document"))
        self.bodyEdit.setPlainText(entity.document.text)
        body_label.setBuddy(self.bodyEdit)

        if self._readOnly:
            self.buttons = QDialogButtonBox(
                QDialogButtonBox.Close, Qt.Horizontal, self
            )
            self.buttons.rejected.connect(self.reject)
        else:
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
        layout.addWidget(propertiesLabel)
        layout.addWidget(self.propertiesTable, 1)
        layout.addLayout(propertyButtons)
        layout.addWidget(body_label)
        layout.addWidget(self.bodyEdit, 1)
        layout.addWidget(self.buttons)

        if self._readOnly:
            self.titleEdit.setReadOnly(True)
            self.typeCombo.setEnabled(False)
            self.aliasesEdit.setReadOnly(True)
            self.propertiesTable.setEditTriggers(
                QTableWidget.NoEditTriggers
            )
            self.addPropertyButton.setVisible(False)
            self.removePropertyButton.setVisible(False)
            self.bodyEdit.setReadOnly(True)

    def _appendProperty(self, name, value):
        row = self.propertiesTable.rowCount()
        self.propertiesTable.insertRow(row)
        nameItem = QTableWidgetItem(str(name))
        valueItem = QTableWidgetItem(self._propertyText(value))
        valueItem.setData(Qt.UserRole, value)
        self.propertiesTable.setItem(row, 0, nameItem)
        self.propertiesTable.setItem(row, 1, valueItem)
        self.propertiesTable.setCurrentCell(row, 0)

    def _removeProperty(self):
        row = self.propertiesTable.currentRow()
        if row >= 0:
            self.propertiesTable.removeRow(row)

    @staticmethod
    def _propertyText(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, indent=2)

    def _metadata(self):
        result = []
        for row in range(self.propertiesTable.rowCount()):
            nameItem = self.propertiesTable.item(row, 0)
            valueItem = self.propertiesTable.item(row, 1)
            name = nameItem.text().strip() if nameItem is not None else ""
            if not name:
                continue
            text = valueItem.text() if valueItem is not None else ""
            original = (
                valueItem.data(Qt.UserRole) if valueItem is not None else ""
            )
            if isinstance(original, str):
                value = text
            else:
                try:
                    value = json.loads(text)
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        self.tr(
                            "Property '{}' must contain valid JSON: {}"
                        ).format(name, error)
                    )
            result.append(StructuredMetadataField(name, value))
        metadata = tuple(result)
        if self._morphologyProfile is not None:
            metadata = self._morphologyProfile.apply_to(metadata)
        return metadata

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
            changes = {
                "title": self.titleEdit.text(),
                "entity_type": str(entity_type),
                "aliases": aliases,
                "text": self.bodyEdit.toPlainText(),
                "metadata": self._metadata(),
            }
            self._saveEntity(self.entity.id, **changes)
        except (KeyError, PermissionError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.tr("Cannot save entity"),
                str(error),
            )
            return False
        self.accept()
        return True

    def submit(self):
        """Commit a window-private draft before its workspace detaches."""

        if self._readOnly:
            return True
        return self.save()

    def _editMorphology(self):
        dialog = MorphologyParadigmDialog(
            self._morphologyProfile,
            self._morphologyProviders,
            self.titleEdit.text() or self.entity.title,
            self,
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        self._morphologyProfile = dialog.profile
        self._morphologyChanged = True
        self._updateMorphologySummary()

    def _updateMorphologySummary(self):
        profile = self._morphologyProfile
        if profile is None:
            text = self.tr("No grammatical forms configured.")
        else:
            provider = (
                self._morphologyProviders.get(profile.provider_id)
                if self._morphologyProviders is not None
                else None
            )
            label = provider.label if provider is not None else profile.provider_id
            text = self.tr("{}; {} name component(s).").format(
                label, len(profile.components)
            )
        self.morphologySummary.setText(text)


class EntityEditorController:
    """Own non-modal child dialogs for one workspace window."""

    def __init__(
        self,
        parent,
        catalog,
        update_entity,
        morphology_providers=None,
        host_panel=None,
        reveal=None,
    ):
        self.parent = parent
        self.catalog = catalog
        self.updateEntity = update_entity
        self.morphologyProviders = morphology_providers
        self.hostPanel = host_panel
        self.reveal = reveal
        self._dialogs = {}

    def open(self, entity_id):
        entity = self.catalog.find(entity_id)
        if entity is None:
            return False
        existing = self._dialogs.get(entity_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            if callable(self.reveal):
                self.reveal()
            return True
        if self.hostPanel is not None and self.hostPanel.editor is not None:
            current = self.hostPanel.editor
            if current.submit() is False:
                return False
        dialog = EntityEditorDialog(
            entity,
            self.catalog.schemas.schemas,
            self.updateEntity,
            self.parent,
            morphology_providers=self.morphologyProviders,
            read_only=(
                not self.catalog.writable
                or entity not in self.catalog.native_entities
            ),
        )
        if self.hostPanel is None:
            dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._dialogs[entity_id] = dialog
        dialog.destroyed.connect(
            lambda _object=None, key=entity_id, dialogs=self._dialogs:
                dialogs.pop(key, None)
        )
        if self.hostPanel is None:
            dialog.show()
        else:
            self.hostPanel.set_editor(dialog)
            if callable(self.reveal):
                self.reveal()
        return True

    def close_all(self):
        if self.hostPanel is not None:
            self.hostPanel.clear()
        else:
            for dialog in tuple(self._dialogs.values()):
                dialog.close()
        self._dialogs.clear()

    def pending_editors(self):
        return tuple(self._dialogs.values())
