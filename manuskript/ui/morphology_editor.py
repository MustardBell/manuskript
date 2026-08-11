"""Accessible editor for deterministic compound-name paradigms."""

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
)

from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)


def default_name_profile(title, provider_id):
    """Create an editable starting point without claiming semantic certainty."""

    words = tuple(value for value in str(title).split() if value)
    components = []
    for index, word in enumerate(words or (str(title).strip() or "Name",)):
        if len(words) > 1 and index == 0:
            role = "given-name"
        elif len(words) > 1 and index == len(words) - 1:
            role = "surname"
        else:
            role = "given-name"
        components.append(MorphologyComponent(
            role,
            word,
            (("gender", "invariable"),),
        ))
    return MorphologyProfile(provider_id, tuple(components))


class MorphologyParadigmDialog(QDialog):
    """Edit components, generated forms, and explicit per-form overrides."""

    def __init__(self, profile, providers, title, parent=None):
        super().__init__(parent)
        self.providers = providers
        available = providers.providers
        if not available:
            raise ValueError("At least one morphology provider is required.")
        if profile is None or providers.get(profile.provider_id) is None:
            profile = default_name_profile(title, available[0].id)
        self._components = list(profile.components)
        self._active = -1
        self._loading = False

        self.setObjectName("morphologyParadigmDialog")
        self.setWindowTitle(self.tr("Name forms — {}").format(title))
        self.setMinimumSize(760, 620)

        self.providerCombo = QComboBox(self)
        self.providerCombo.setObjectName("morphologyProviderCombo")
        self.providerCombo.setAccessibleName(self.tr("Language provider"))
        for provider in available:
            self.providerCombo.addItem(provider.label, provider.id)
        self.providerCombo.setCurrentIndex(
            self.providerCombo.findData(profile.provider_id)
        )

        self.componentCombo = QComboBox(self)
        self.componentCombo.setObjectName("morphologyComponentCombo")
        self.componentCombo.setAccessibleName(self.tr("Name component"))
        self.addButton = QPushButton(self.tr("&Add component"), self)
        self.removeButton = QPushButton(self.tr("&Remove component"), self)

        component_row = QHBoxLayout()
        component_row.addWidget(self.componentCombo, 1)
        component_row.addWidget(self.addButton)
        component_row.addWidget(self.removeButton)

        self.roleCombo = QComboBox(self)
        self.roleCombo.setObjectName("morphologyRoleCombo")
        self.roleCombo.setEditable(True)
        self.lemmaEdit = QLineEdit(self)
        self.lemmaEdit.setObjectName("morphologyLemmaEdit")
        self.lemmaEdit.setAccessibleName(self.tr("Dictionary form"))
        self.genderCombo = QComboBox(self)
        self.genderCombo.setObjectName("morphologyGenderCombo")

        component_form = QFormLayout()
        component_form.addRow(self.tr("&Role:"), self.roleCombo)
        component_form.addRow(self.tr("&Dictionary form:"), self.lemmaEdit)
        component_form.addRow(self.tr("&Gender:"), self.genderCombo)

        help_label = QLabel(self.tr(
            "Generated forms are deterministic suggestions. Review them and "
            "enter an override wherever the language rule is wrong."
        ), self)
        help_label.setWordWrap(True)

        self.formsTable = QTableWidget(0, 3, self)
        self.formsTable.setObjectName("morphologyFormsTable")
        self.formsTable.setAccessibleName(
            self.tr("Generated forms and author overrides")
        )
        self.formsTable.setHorizontalHeaderLabels((
            self.tr("Form"), self.tr("Generated"), self.tr("Override")
        ))
        self.formsTable.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.formsTable.horizontalHeader().setStretchLastSection(True)

        preview_label = QLabel(self.tr("Compound-name preview"), self)
        self.validationLabel = QLabel(self)
        self.validationLabel.setObjectName("morphologyValidation")
        self.validationLabel.setAccessibleName(
            self.tr("Morphology validation")
        )
        self.validationLabel.setWordWrap(True)
        self.previewTable = QTableWidget(0, 2, self)
        self.previewTable.setObjectName("morphologyCompoundPreview")
        self.previewTable.setAccessibleName(
            self.tr("Generated compound-name forms")
        )
        self.previewTable.setHorizontalHeaderLabels((
            self.tr("Form"), self.tr("Complete name")
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
        provider_form = QFormLayout()
        provider_form.addRow(self.tr("&Language provider:"), self.providerCombo)
        layout.addLayout(provider_form)
        layout.addLayout(component_row)
        layout.addLayout(component_form)
        layout.addWidget(help_label)
        layout.addWidget(self.formsTable, 1)
        layout.addWidget(self.validationLabel)
        layout.addWidget(preview_label)
        layout.addWidget(self.previewTable, 1)
        layout.addWidget(self.buttons)

        self.providerCombo.currentIndexChanged.connect(
            self._provider_changed
        )
        self.componentCombo.currentIndexChanged.connect(
            self._component_changed
        )
        self.addButton.clicked.connect(self._add_component)
        self.removeButton.clicked.connect(self._remove_component)
        self.lemmaEdit.textEdited.connect(self._component_field_changed)
        self.roleCombo.currentTextChanged.connect(
            self._component_field_changed
        )
        self.genderCombo.currentIndexChanged.connect(
            self._component_field_changed
        )
        self.formsTable.itemChanged.connect(self._override_changed)

        self._load_provider_controls()
        self._refresh_component_choices(0)

    @property
    def profile(self):
        self._save_active_component()
        return MorphologyProfile(
            str(self.providerCombo.currentData()),
            tuple(self._components),
        )

    def _provider(self):
        return self.providers.get(str(self.providerCombo.currentData()))

    def _load_provider_controls(self):
        provider = self._provider()
        current_role = self.roleCombo.currentText()
        current_gender = self.genderCombo.currentData()
        self._loading = True
        self.roleCombo.clear()
        self.genderCombo.clear()
        if provider is not None:
            for value, label in provider.component_roles:
                self.roleCombo.addItem(label, value)
            for value, label in provider.genders:
                self.genderCombo.addItem(label, value)
        self._set_combo_value(self.roleCombo, current_role, by_data=True)
        self._set_combo_value(self.genderCombo, current_gender, by_data=True)
        self._loading = False

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
        self._loading = True
        self._set_combo_value(self.roleCombo, component.role, by_data=True)
        self.lemmaEdit.setText(component.lemma)
        self._set_combo_value(
            self.genderCombo,
            component.attribute("gender", "invariable"),
            by_data=True,
        )
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
        gender = str(self.genderCombo.currentData() or "invariable")
        self._components[self._active] = replace(
            component,
            role=role,
            lemma=self.lemmaEdit.text().strip(),
            attributes=(("gender", gender),),
        )

    def _refresh_forms(self):
        provider = self._provider()
        if provider is None or not (0 <= self._active < len(self._components)):
            return
        component = self._components[self._active]
        forms = provider.generate(component)
        self._loading = True
        self.formsTable.setRowCount(len(forms))
        for row, form in enumerate(forms):
            label = QTableWidgetItem(form.label)
            label.setData(Qt.UserRole, form.key)
            label.setFlags(label.flags() & ~Qt.ItemIsEditable)
            generated = QTableWidgetItem(form.text)
            generated.setFlags(generated.flags() & ~Qt.ItemIsEditable)
            override = QTableWidgetItem(component.override(form.key) or "")
            self.formsTable.setItem(row, 0, label)
            self.formsTable.setItem(row, 1, generated)
            self.formsTable.setItem(row, 2, override)
        self._loading = False
        self._refresh_preview()

    def _override_changed(self, item):
        if self._loading or item.column() != 2:
            return
        component = self._components[self._active]
        key_item = self.formsTable.item(item.row(), 0)
        key = str(key_item.data(Qt.UserRole))
        overrides = dict(component.overrides)
        value = item.text().strip()
        if value:
            overrides[key] = value
        else:
            overrides.pop(key, None)
        self._components[self._active] = replace(
            component, overrides=tuple(overrides.items())
        )
        self._refresh_preview()

    def _refresh_preview(self):
        profile = MorphologyProfile(
            str(self.providerCombo.currentData()), tuple(self._components)
        )
        issues = self.providers.validate(profile)
        self.validationLabel.setText(
            self.tr("Configuration is valid.")
            if not issues
            else self.tr("Cannot generate complete forms: {}").format(
                " ".join(issue.message for issue in issues)
            )
        )
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not issues)
        forms = self.providers.generate(profile)
        self.previewTable.setRowCount(len(forms))
        for row, form in enumerate(forms):
            self.previewTable.setItem(row, 0, QTableWidgetItem(form.label))
            self.previewTable.setItem(row, 1, QTableWidgetItem(form.text))

    def _provider_changed(self, _index):
        if self._loading:
            return
        self._save_active_component()
        self._load_provider_controls()
        self._component_changed(self._active)

    def _add_component(self):
        self._save_active_component()
        self._components.append(MorphologyComponent(
            "given-name", "Name", (("gender", "invariable"),)
        ))
        self._refresh_component_choices(len(self._components) - 1)

    def _remove_component(self):
        if len(self._components) <= 1:
            return
        index = self._active
        self._components.pop(index)
        self._active = -1
        self._refresh_component_choices(min(index, len(self._components) - 1))

    def _accept_profile(self):
        self._save_active_component()
        if not all(component.lemma for component in self._components):
            self.lemmaEdit.setFocus()
            return
        self.accept()

    @staticmethod
    def _set_combo_value(combo, value, *, by_data=False):
        if value is None:
            return
        index = combo.findData(value) if by_data else combo.findText(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)
        elif combo.isEditable():
            combo.setEditText(str(value))
