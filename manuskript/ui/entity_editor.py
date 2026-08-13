"""Window-local editor for one canonical entity document."""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
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
from manuskript.domain.entity_catalog import CHOICE, FLAG, TEXT
from manuskript.domain.morphology import MorphologyProfile
from manuskript.ui.morphology_editor import MorphologyParadigmDialog

#: What a stored flag may say for "yes". Format 1 wrote Python booleans.
_TRUE = ("true", "1", "yes", "on")

#: How wide a field whose content has a known short bound may get.
BOUNDED_FIELD_WIDTH = 300


def _ordered_sections(fields):
    """Section names in the order their first field declares them."""
    names = []
    for spec in fields:
        if spec.section not in names:
            names.append(spec.section)
    return names


def _make_read_only(widget):
    if isinstance(widget, (QCheckBox, QComboBox)):
        widget.setEnabled(False)
    else:
        widget.setReadOnly(True)


class EntityEditorDialog(QDialog):
    """Edit generic entity fields without knowing any story semantics."""

    def __init__(
        self,
        entity,
        schemas,
        save_entity,
        parent=None,
        morphology_schemas=None,
        read_only=False,
    ):
        super().__init__(parent)
        self.entity = entity
        self._saveEntity = save_entity
        self._morphologySchemas = morphology_schemas
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
        for known in schemas:
            self.typeCombo.addItem(known.label, known.type)
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
        self.morphologyButton.setEnabled(
            not self._readOnly
            and morphology_schemas is not None
        )
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

        # What this kind of entity is expected to carry, laid out as its
        # own fields. Without this the only editor possible is a table of
        # raw keys, and a character editor stops being one.
        self._schema = schema
        self._fieldWidgets = {}
        self._fieldPresent = set()
        self._schemaSections = self._buildSchemaSections(entity)

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
            if (
                field.name in self._fieldWidgets
                or (
                    field.name == "morphology"
                    and self._morphologyProfile is not None
                )
            ):
                # Shown as its own field above. Repeating it here as a
                # raw key would offer two places to edit one value.
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
        for section in self._schemaSections:
            layout.addWidget(section)
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

    def _buildSchemaSections(self, entity):
        """One group box per section of fields this schema declares."""
        schema = self._schema
        if schema is None or not schema.fields:
            return ()
        stored = {field.name: field.value for field in entity.metadata}
        #: Which declared fields the entity already carried, so saving
        #: adds nothing it did not have and had nothing to say about.
        self._fieldPresent = set(stored)
        sections = []
        for name in _ordered_sections(schema.fields):
            box = QGroupBox(
                name or self.tr("Details"), self,
            )
            box.setObjectName("entitySection." + (name or "details"))
            box_form = QFormLayout(box)
            for spec in schema.fields:
                if spec.section != name:
                    continue
                widget = self._buildFieldWidget(spec, stored.get(spec.name))
                self._fieldWidgets[spec.name] = (spec, widget)
                if spec.kind == FLAG:
                    box_form.addRow("", widget)
                else:
                    box_form.addRow(spec.label + ":", widget)
            sections.append(box)
        return tuple(sections)

    def _buildFieldWidget(self, spec, value):
        text = "" if value is None else str(value)
        if spec.kind == FLAG:
            widget = QCheckBox(spec.label, self)
            widget.setChecked(text.strip().casefold() in _TRUE)
        elif spec.kind == CHOICE:
            widget = QComboBox(self)
            for entry, label in spec.choices:
                widget.addItem(label, entry)
            index = widget.findData(text)
            if index < 0 and text:
                # A value this schema does not list is still the value
                # the project holds; offering it keeps saving lossless.
                widget.addItem(text, text)
                index = widget.count() - 1
            if index < 0:
                # Nothing recorded. An empty choice says so, where
                # falling back to the first would quietly make every
                # character a main one the moment it was opened.
                widget.insertItem(0, "", "")
                index = 0
            widget.setCurrentIndex(index)
        elif spec.kind == TEXT:
            widget = QPlainTextEdit(self)
            widget.setPlainText(text)
            widget.setMinimumHeight(56)
        else:
            widget = QLineEdit(self)
            widget.setText(text)
        if spec.kind in (CHOICE, FLAG):
            # Its content has a known short bound, so it does not earn
            # the whole field column the way prose does.
            widget.setMaximumWidth(BOUNDED_FIELD_WIDTH)
        widget.setObjectName("entityField." + spec.name)
        widget.setAccessibleName(spec.label)
        if self._readOnly:
            _make_read_only(widget)
        return widget

    def _schemaValues(self):
        """What the declared fields now say, by their stored names."""
        values = {}
        for name, (spec, widget) in self._fieldWidgets.items():
            if spec.kind == FLAG:
                # A box has no "not set", so an unticked one only says
                # False where the entity already had an answer. On one
                # that never did, it stays unanswered rather than
                # writing a decision nobody made.
                if widget.isChecked():
                    values[name] = "True"
                else:
                    values[name] = "False" if name in self._fieldPresent else ""
            elif spec.kind == CHOICE:
                data = widget.currentData()
                values[name] = (
                    widget.currentText() if data is None else str(data)
                )
            elif spec.kind == TEXT:
                values[name] = widget.toPlainText()
            else:
                values[name] = widget.text()
        return values

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
        # The declared fields lead, in the order the schema names them,
        # so a character's file reads the way a character reads.
        declared = self._schemaValues()
        ordered = [
            StructuredMetadataField(spec.name, declared[spec.name])
            for spec, _widget in self._fieldWidgets.values()
            if spec.name in declared
            # An empty field is an absent one. Writing all nine of them
            # into every character would fill each file with keys that
            # say nothing and rewrite files nobody edited.
            and (
                str(declared[spec.name]).strip()
                or spec.name in self._fieldPresent
            )
        ]
        metadata = tuple(ordered) + tuple(result)
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
            self._morphologySchemas,
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
            schema = (
                self._morphologySchemas.get(profile.schema_id)
                if self._morphologySchemas is not None
                else None
            )
            label = schema.label if schema is not None else (
                profile.schema_id or profile.language_tag
            )
            text = self.tr("{}; {} component(s).").format(
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
        morphology_schemas=None,
        host_panel=None,
        reveal=None,
    ):
        self.parent = parent
        self.catalog = catalog
        self.updateEntity = update_entity
        self.morphologySchemas = morphology_schemas
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
            morphology_schemas=self.morphologySchemas,
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
