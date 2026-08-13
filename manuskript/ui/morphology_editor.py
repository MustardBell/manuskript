"""Schema-driven editor for morphology packs and opaque author overrides."""

from dataclasses import replace

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from manuskript.domain.morphology import (
    CHOICE,
    MorphologyComponent,
    MorphologyProfile,
    normalize_language_tag,
)


def default_morphology_profile(title, schema=None):
    """Start without inferring linguistic structure from an entity title."""

    role = schema.default_role if schema is not None else ""
    attributes = schema.defaults() if schema is not None else ()
    language = schema.language_tag if schema is not None else "und"
    schema_id = schema.id if schema is not None else ""
    return MorphologyProfile(
        language,
        schema_id,
        (MorphologyComponent(role, str(title).strip() or "Lexeme", attributes),),
    )


class MorphologyParadigmDialog(QDialog):
    """Edit schema features and manual forms without knowing their meaning."""

    def __init__(self, profile, schemas, title, parent=None):
        super().__init__(parent)
        self.schemas = schemas
        available = schemas.schemas
        if profile is None:
            profile = default_morphology_profile(title)
        self._components = list(profile.components)
        self._active = -1
        self._loading = False
        self._attributeWidgets = {}

        self.setObjectName("morphologyParadigmDialog")
        self.setWindowTitle(self.tr("Grammatical forms — {}").format(title))
        self.setMinimumSize(800, 680)

        self.languageEdit = QLineEdit(profile.language_tag, self)
        self.languageEdit.setObjectName("morphologyLanguageTag")
        self.languageEdit.setAccessibleName(self.tr("BCP 47 language tag"))
        self.schemaCombo = QComboBox(self)
        self.schemaCombo.setObjectName("morphologySchemaCombo")
        self.schemaCombo.setAccessibleName(self.tr("Morphology schema"))
        self.schemaCombo.addItem(self.tr("Manual forms (no schema)"), "")
        for schema in available:
            self.schemaCombo.addItem(schema.label, schema.id)
        schema_index = self.schemaCombo.findData(profile.schema_id)
        if schema_index < 0 and profile.schema_id:
            self.schemaCombo.addItem(
                self.tr("Unavailable schema: {}").format(profile.schema_id),
                profile.schema_id,
            )
            schema_index = self.schemaCombo.count() - 1
        self.schemaCombo.setCurrentIndex(max(schema_index, 0))

        identity = QFormLayout()
        identity.addRow(self.tr("&Language tag:"), self.languageEdit)
        identity.addRow(self.tr("&Schema:"), self.schemaCombo)

        self.componentCombo = QComboBox(self)
        self.componentCombo.setObjectName("morphologyComponentCombo")
        self.componentCombo.setAccessibleName(self.tr("Morphology component"))
        self.addButton = QPushButton(self.tr("&Add component"), self)
        self.removeButton = QPushButton(self.tr("&Remove component"), self)
        component_row = QHBoxLayout()
        component_row.addWidget(self.componentCombo, 1)
        component_row.addWidget(self.addButton)
        component_row.addWidget(self.removeButton)

        self.roleCombo = QComboBox(self)
        self.roleCombo.setObjectName("morphologyRoleCombo")
        self.roleCombo.setEditable(True)
        self.roleCombo.setAccessibleName(self.tr("Component role"))
        self.lemmaEdit = QLineEdit(self)
        self.lemmaEdit.setObjectName("morphologyLemmaEdit")
        self.lemmaEdit.setAccessibleName(self.tr("Dictionary form"))
        component_form = QFormLayout()
        component_form.addRow(self.tr("&Role:"), self.roleCombo)
        component_form.addRow(self.tr("&Dictionary form:"), self.lemmaEdit)

        self.attributeWidget = QWidget(self)
        self.attributeForm = QFormLayout(self.attributeWidget)
        self.attributeForm.setContentsMargins(0, 0, 0, 0)
        self.extraAttributes = QTableWidget(0, 2, self)
        self.extraAttributes.setObjectName("morphologyAdditionalFeatures")
        self.extraAttributes.setAccessibleName(
            self.tr("Additional morphology features")
        )
        self.extraAttributes.setHorizontalHeaderLabels((
            self.tr("Feature"), self.tr("Value")
        ))
        self.extraAttributes.horizontalHeader().setStretchLastSection(True)
        self.extraAttributes.verticalHeader().setVisible(False)
        self.extraAttributes.setMaximumHeight(150)
        self.extraAttributes.setVisible(False)
        self.addAttributeButton = QPushButton(self.tr("Add f&eature"), self)
        self.removeAttributeButton = QPushButton(
            self.tr("Remove feature"), self
        )
        self.removeAttributeButton.setVisible(False)
        attribute_buttons = QHBoxLayout()
        attribute_buttons.addWidget(self.addAttributeButton)
        attribute_buttons.addWidget(self.removeAttributeButton)
        attribute_buttons.addStretch(1)

        help_label = QLabel(self.tr(
            "The selected pack describes fields and generated forms. Author "
            "overrides are authoritative and remain editable without the pack."
        ), self)
        help_label.setWordWrap(True)

        self.formsTable = QTableWidget(0, 4, self)
        self.formsTable.setObjectName("morphologyFormsTable")
        self.formsTable.setAccessibleName(
            self.tr("Generated forms and author overrides")
        )
        self.formsTable.setHorizontalHeaderLabels((
            self.tr("Key"), self.tr("Form"), self.tr("Generated"),
            self.tr("Override")
        ))
        self.formsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.formsTable.horizontalHeader().setStretchLastSection(True)
        self.addFormButton = QPushButton(self.tr("Add &manual form"), self)
        self.removeFormButton = QPushButton(self.tr("Remove manual form"), self)
        form_buttons = QHBoxLayout()
        form_buttons.addWidget(self.addFormButton)
        form_buttons.addWidget(self.removeFormButton)
        form_buttons.addStretch(1)

        preview_label = QLabel(self.tr("Complete-expression preview"), self)
        self.validationLabel = QLabel(self)
        self.validationLabel.setObjectName("morphologyValidation")
        self.validationLabel.setAccessibleName(self.tr("Morphology validation"))
        self.validationLabel.setWordWrap(True)
        self.previewTable = QTableWidget(0, 2, self)
        self.previewTable.setObjectName("morphologyCompoundPreview")
        self.previewTable.setAccessibleName(
            self.tr("Generated complete-expression forms")
        )
        self.previewTable.setHorizontalHeaderLabels((
            self.tr("Form"), self.tr("Complete expression")
        ))
        self.previewTable.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.previewTable.horizontalHeader().setStretchLastSection(True)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self._accept_profile)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(identity)
        layout.addLayout(component_row)
        layout.addLayout(component_form)
        layout.addWidget(self.attributeWidget)
        layout.addWidget(self.extraAttributes)
        layout.addLayout(attribute_buttons)
        layout.addWidget(help_label)
        layout.addWidget(self.formsTable, 1)
        layout.addLayout(form_buttons)
        layout.addWidget(self.validationLabel)
        layout.addWidget(preview_label)
        layout.addWidget(self.previewTable, 1)
        layout.addWidget(self.buttons)

        self.schemaCombo.currentIndexChanged.connect(self._schema_changed)
        self.languageEdit.textChanged.connect(self._refresh_preview)
        self.componentCombo.currentIndexChanged.connect(self._component_changed)
        self.addButton.clicked.connect(self._add_component)
        self.removeButton.clicked.connect(self._remove_component)
        self.lemmaEdit.textEdited.connect(self._component_field_changed)
        self.roleCombo.currentTextChanged.connect(self._component_field_changed)
        self.extraAttributes.itemChanged.connect(self._component_field_changed)
        self.formsTable.itemChanged.connect(self._form_changed)
        self.addAttributeButton.clicked.connect(self._add_attribute)
        self.removeAttributeButton.clicked.connect(self._remove_attribute)
        self.addFormButton.clicked.connect(self._add_form)
        self.removeFormButton.clicked.connect(self._remove_form)

        self._load_schema_controls()
        self._refresh_component_choices(0)

    @property
    def profile(self):
        self._save_active_component()
        return MorphologyProfile(
            self.languageEdit.text(),
            str(self.schemaCombo.currentData() or ""),
            tuple(self._components),
        )

    def _schema(self):
        return self.schemas.get(str(self.schemaCombo.currentData() or ""))

    def _load_schema_controls(self):
        schema = self._schema()
        current_role = self.roleCombo.currentData()
        current_role = current_role or self.roleCombo.currentText()
        self._loading = True
        self.roleCombo.clear()
        if schema is not None:
            for value, label in schema.component_roles:
                self.roleCombo.addItem(label, value)
        self._set_combo_value(self.roleCombo, current_role, by_data=True)
        self._clear_attribute_form()
        if schema is not None:
            for field in schema.attributes:
                if field.kind == CHOICE:
                    widget = QComboBox(self.attributeWidget)
                    for value, label in field.choices:
                        widget.addItem(label, value)
                    widget.currentIndexChanged.connect(
                        self._component_field_changed
                    )
                else:
                    widget = QLineEdit(self.attributeWidget)
                    widget.textEdited.connect(self._component_field_changed)
                widget.setObjectName("morphologyFeature." + field.key)
                widget.setAccessibleName(field.label)
                self._attributeWidgets[field.key] = (field, widget)
                self.attributeForm.addRow(field.label + ":", widget)
        self.attributeWidget.setVisible(bool(self._attributeWidgets))
        self._loading = False

    def _clear_attribute_form(self):
        while self.attributeForm.count():
            item = self.attributeForm.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._attributeWidgets = {}

    def _refresh_component_choices(self, selected):
        self._loading = True
        self.componentCombo.clear()
        for index, component in enumerate(self._components):
            self.componentCombo.addItem(
                "{} — {}".format(index + 1, component.lemma), index
            )
        self._loading = False
        self.componentCombo.setCurrentIndex(
            min(max(selected, 0), len(self._components) - 1)
        )
        self.removeButton.setEnabled(len(self._components) > 1)
        self._component_changed(self.componentCombo.currentIndex())

    def _component_changed(self, index):
        if self._loading:
            return
        self._save_active_component()
        self._active = int(index)
        if self._active < 0 or self._active >= len(self._components):
            return
        component = self._components[self._active]
        schema = self._schema()
        known = {field.key for field in (() if schema is None else schema.attributes)}
        values = dict(component.attributes)
        self._loading = True
        self._set_combo_value(self.roleCombo, component.role, by_data=True)
        self.lemmaEdit.setText(component.lemma)
        for key, (field, widget) in self._attributeWidgets.items():
            value = values.get(key, field.default)
            if isinstance(widget, QComboBox):
                self._set_combo_value(widget, value, by_data=True)
            else:
                widget.setText(value)
        self.extraAttributes.setRowCount(0)
        for key, value in component.attributes:
            if key not in known:
                self._append_pair(self.extraAttributes, key, value)
        has_extra = self.extraAttributes.rowCount() > 0
        self.extraAttributes.setVisible(has_extra)
        self.removeAttributeButton.setVisible(has_extra)
        self._loading = False
        self._refresh_forms()

    def _component_field_changed(self, *_args):
        if self._loading:
            return
        self._save_active_component()
        self._refresh_component_choices(self._active)

    def _save_active_component(self):
        if self._loading or not (0 <= self._active < len(self._components)):
            return
        component = self._components[self._active]
        role = self.roleCombo.currentData()
        role = str(role if role is not None else self.roleCombo.currentText())
        attributes = {}
        for key, (_field, widget) in self._attributeWidgets.items():
            attributes[key] = str(
                widget.currentData() if isinstance(widget, QComboBox)
                else widget.text()
            )
        attributes.update(self._pairs(self.extraAttributes))
        overrides = self._form_overrides()
        self._components[self._active] = replace(
            component,
            role=role,
            lemma=self.lemmaEdit.text().strip(),
            attributes=tuple(attributes.items()),
            overrides=tuple(overrides.items()),
        )

    def _refresh_forms(self):
        if not (0 <= self._active < len(self._components)):
            return
        component = self._components[self._active]
        generated = self.schemas.generate_component(
            str(self.schemaCombo.currentData() or ""), component
        )
        generated_by_key = {form.key: form for form in generated}
        keys = [form.key for form in generated]
        for key, _value in component.overrides:
            if key not in keys:
                keys.append(key)
        overrides = dict(component.overrides)
        self._loading = True
        self.formsTable.setRowCount(len(keys))
        for row, key in enumerate(keys):
            form = generated_by_key.get(key)
            key_item = QTableWidgetItem(key)
            if form is not None:
                key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            label = QTableWidgetItem(form.label if form is not None else key)
            label.setFlags(label.flags() & ~Qt.ItemIsEditable)
            generated_item = QTableWidgetItem(form.text if form is not None else "")
            generated_item.setFlags(generated_item.flags() & ~Qt.ItemIsEditable)
            self.formsTable.setItem(row, 0, key_item)
            self.formsTable.setItem(row, 1, label)
            self.formsTable.setItem(row, 2, generated_item)
            self.formsTable.setItem(row, 3, QTableWidgetItem(overrides.get(key, "")))
        self._loading = False
        self._refresh_preview()

    def _form_changed(self, _item):
        if self._loading:
            return
        self._save_active_component()
        self._refresh_preview()

    def _form_overrides(self):
        result = {}
        for row in range(self.formsTable.rowCount()):
            key_item = self.formsTable.item(row, 0)
            value_item = self.formsTable.item(row, 3)
            key = "" if key_item is None else key_item.text().strip()
            value = "" if value_item is None else value_item.text().strip()
            if key and value:
                result[key] = value
        return result

    def _refresh_preview(self, *_args):
        try:
            profile = self.profile
        except ValueError as error:
            self.validationLabel.setText(str(error))
            self.previewTable.setRowCount(0)
            self.buttons.button(QDialogButtonBox.Save).setEnabled(False)
            return
        issues = self.schemas.validate(profile)
        blocking = any(issue.blocking for issue in issues)
        self.validationLabel.setText(
            self.tr("Configuration is valid.")
            if not issues
            else " ".join(issue.message for issue in issues)
        )
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not blocking)
        forms = self.schemas.generate(profile)
        self.previewTable.setRowCount(len(forms))
        for row, form in enumerate(forms):
            self.previewTable.setItem(row, 0, QTableWidgetItem(form.label))
            self.previewTable.setItem(row, 1, QTableWidgetItem(form.text))

    def _schema_changed(self, _index):
        if self._loading:
            return
        self._save_active_component()
        schema = self._schema()
        if schema is not None:
            self.languageEdit.setText(schema.language_tag)
            updated = []
            for component in self._components:
                attributes = dict(schema.defaults())
                attributes.update(component.attributes)
                updated.append(replace(
                    component,
                    role=component.role or schema.default_role,
                    attributes=tuple(attributes.items()),
                ))
            self._components = updated
        selected = self._active
        # The new widgets initially contain their first choices.  They must
        # not be mistaken for author input before the selected component has
        # populated them.
        self._active = -1
        self._load_schema_controls()
        self._component_changed(selected)

    def _add_component(self):
        self._save_active_component()
        schema = self._schema()
        self._components.append(MorphologyComponent(
            schema.default_role if schema is not None else "",
            "Lexeme",
            schema.defaults() if schema is not None else (),
        ))
        self._refresh_component_choices(len(self._components) - 1)

    def _remove_component(self):
        if len(self._components) <= 1:
            return
        index = self._active
        self._components.pop(index)
        self._active = -1
        self._refresh_component_choices(min(index, len(self._components) - 1))

    def _add_attribute(self):
        self.extraAttributes.setVisible(True)
        self.removeAttributeButton.setVisible(True)
        self._append_pair(self.extraAttributes, "", "")

    def _remove_attribute(self):
        row = self.extraAttributes.currentRow()
        if row >= 0:
            self.extraAttributes.removeRow(row)
            has_extra = self.extraAttributes.rowCount() > 0
            self.extraAttributes.setVisible(has_extra)
            self.removeAttributeButton.setVisible(has_extra)
            self._component_field_changed()

    def _add_form(self):
        row = self.formsTable.rowCount()
        self.formsTable.insertRow(row)
        self.formsTable.setItem(row, 0, QTableWidgetItem(""))
        label = QTableWidgetItem(self.tr("Manual form"))
        label.setFlags(label.flags() & ~Qt.ItemIsEditable)
        generated = QTableWidgetItem("")
        generated.setFlags(generated.flags() & ~Qt.ItemIsEditable)
        self.formsTable.setItem(row, 1, label)
        self.formsTable.setItem(row, 2, generated)
        self.formsTable.setItem(row, 3, QTableWidgetItem(""))
        self.formsTable.setCurrentCell(row, 0)

    def _remove_form(self):
        row = self.formsTable.currentRow()
        if row < 0:
            return
        key = self.formsTable.item(row, 0)
        generated = self.schemas.generate_component(
            str(self.schemaCombo.currentData() or ""),
            self._components[self._active],
        )
        if key is not None and key.text() in {item.key for item in generated}:
            self.formsTable.item(row, 3).setText("")
        else:
            self.formsTable.removeRow(row)
        self._form_changed(None)

    def _accept_profile(self):
        self._save_active_component()
        if not all(component.lemma for component in self._components):
            self.lemmaEdit.setFocus()
            return
        try:
            normalize_language_tag(self.languageEdit.text())
        except ValueError:
            self.languageEdit.setFocus()
            return
        self.accept()

    @staticmethod
    def _append_pair(table, key, value):
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(str(key)))
        table.setItem(row, 1, QTableWidgetItem(str(value)))

    @staticmethod
    def _pairs(table):
        result = {}
        for row in range(table.rowCount()):
            key_item = table.item(row, 0)
            value_item = table.item(row, 1)
            key = "" if key_item is None else key_item.text().strip()
            value = "" if value_item is None else value_item.text()
            if key:
                result[key] = value
        return result

    @staticmethod
    def _set_combo_value(combo, value, *, by_data=False):
        if value is None:
            return
        index = combo.findData(value) if by_data else combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setEditText(str(value))
