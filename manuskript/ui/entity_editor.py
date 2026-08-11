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
    QPushButton,
    QVBoxLayout,
)

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
    ):
        super().__init__(parent)
        self.entity = entity
        self._saveEntity = save_entity
        self._morphologyProviders = morphology_providers
        self._morphologyProfile = MorphologyProfile.from_entity(entity)
        self._morphologyChanged = False
        self.setObjectName("entityEditorDialog")
        self.setWindowTitle(self.tr("Entity — {}").format(entity.title))
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
        changes = {
            "title": self.titleEdit.text(),
            "entity_type": str(entity_type),
            "aliases": aliases,
            "text": self.bodyEdit.toPlainText(),
        }
        if self._morphologyChanged and self._morphologyProfile is not None:
            changes["metadata"] = self._morphologyProfile.apply_to(
                self.entity.metadata
            )
        try:
            self._saveEntity(self.entity.id, **changes)
        except (KeyError, PermissionError, ValueError) as error:
            QMessageBox.warning(
                self,
                self.tr("Cannot save entity"),
                str(error),
            )
            return
        self.accept()

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
        self, parent, catalog, update_entity, morphology_providers=None
    ):
        self.parent = parent
        self.catalog = catalog
        self.updateEntity = update_entity
        self.morphologyProviders = morphology_providers
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
            morphology_providers=self.morphologyProviders,
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        self._dialogs[entity_id] = dialog
        dialog.destroyed.connect(
            lambda _object=None, key=entity_id, dialogs=self._dialogs:
                dialogs.pop(key, None)
        )
        dialog.show()
        return True
