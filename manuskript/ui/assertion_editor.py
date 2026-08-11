"""Author-facing editor for one explicit source-owned story assertion."""

import uuid

import yaml
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from manuskript.domain.story_assertions import (
    Assertion,
    AssertionProvenance,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
    TemporalAxis,
    TemporalInterval,
    TemporalPoint,
)


COMMON_PREDICATES = (
    "appears_in",
    "causes",
    "knows",
    "located_at",
    "possesses",
    "related_to",
    "trusts",
)


class AssertionEditorDialog(QDialog):
    """Collect an explicit claim; it never analyses manuscript prose."""

    def __init__(
        self,
        current_document,
        entity_choices,
        parent=None,
        id_factory=None,
        temporal_choices=(),
        temporal_enabled=False,
    ):
        super().__init__(parent)
        self._idFactory = id_factory or (lambda: str(uuid.uuid4()))
        self._assertionId = str(self._idFactory())
        self.setObjectName("assertionEditorDialog")
        self.setWindowTitle(self.tr("Add story assertion"))
        self.setMinimumSize(600, 620)

        references = [(
            self.tr("Current document"), current_document
        )]
        references.extend(
            (
                "{} ({})".format(choice.title, choice.entity_type),
                StoryReference("entity", choice.entity_id),
            )
            for choice in entity_choices
        )

        self.subjectCombo = QComboBox(self)
        self.subjectCombo.setObjectName("assertionSubjectCombo")
        self.subjectCombo.setAccessibleName(self.tr("Assertion subject"))
        self.objectReferenceCombo = QComboBox(self)
        self.objectReferenceCombo.setObjectName("assertionObjectReferenceCombo")
        self.objectReferenceCombo.setAccessibleName(
            self.tr("Assertion object reference")
        )
        for label, reference in references:
            self.subjectCombo.addItem(label, reference)
            self.objectReferenceCombo.addItem(label, reference)

        self.predicateCombo = QComboBox(self)
        self.predicateCombo.setObjectName("assertionPredicateCombo")
        self.predicateCombo.setEditable(True)
        self.predicateCombo.setAccessibleName(self.tr("Assertion predicate"))
        self.predicateCombo.addItems(COMMON_PREDICATES)

        self.objectKindCombo = QComboBox(self)
        self.objectKindCombo.setObjectName("assertionObjectKindCombo")
        self.objectKindCombo.addItem(self.tr("Reference"), "reference")
        self.objectKindCombo.addItem(self.tr("Value"), "value")
        self.objectKindCombo.setAccessibleName(
            self.tr("Assertion object kind")
        )
        self.objectValueEdit = QLineEdit(self)
        self.objectValueEdit.setObjectName("assertionObjectValueEdit")
        self.objectValueEdit.setAccessibleName(
            self.tr("Assertion scalar value")
        )
        self.objectStack = QStackedWidget(self)
        self.objectStack.addWidget(self.objectReferenceCombo)
        value_page = QWidget(self.objectStack)
        value_layout = QVBoxLayout(value_page)
        value_layout.setContentsMargins(0, 0, 0, 0)
        value_layout.addWidget(self.objectValueEdit)
        self.objectStack.addWidget(value_page)

        self.canonCombo = QComboBox(self)
        self.canonCombo.setObjectName("assertionCanonCombo")
        self.canonCombo.setAccessibleName(self.tr("Assertion canon state"))
        for state in CanonState:
            self.canonCombo.addItem(
                state.value.replace("-", " ").title(), state
            )

        self._temporalChoices = tuple(temporal_choices)
        self.validityAxisCombo = QComboBox(self)
        self.validityAxisCombo.setObjectName("assertionValidityAxisCombo")
        self.validityAxisCombo.setAccessibleName(
            self.tr("Assertion temporal scope")
        )
        self.validityAxisCombo.addItem(self.tr("No temporal scope"), None)
        self.validityAxisCombo.addItem(
            self.tr("Narrative order"), TemporalAxis.NARRATIVE
        )
        self.validityAxisCombo.addItem(
            self.tr("Story chronology"), TemporalAxis.STORY
        )
        self.validityAxisCombo.setEnabled(bool(temporal_enabled))
        self.validityFromCombo = self._temporal_combo(
            "assertionValidityFromCombo", self.tr("Valid from")
        )
        self.validityUntilCombo = self._temporal_combo(
            "assertionValidityUntilCombo", self.tr("Valid until")
        )

        self.qualifiersEdit = QPlainTextEdit(self)
        self.qualifiersEdit.setObjectName("assertionQualifiersEdit")
        self.qualifiersEdit.setAccessibleName(
            self.tr("Assertion qualifiers as YAML")
        )
        self.qualifiersEdit.setPlaceholderText(
            self.tr("Optional YAML mapping, for example:\ncertainty: explicit")
        )
        self.qualifiersEdit.setMaximumHeight(110)
        self.anchorEdit = QLineEdit(self)
        self.anchorEdit.setObjectName("assertionAnchorEdit")
        self.anchorEdit.setAccessibleName(self.tr("Provenance anchor"))
        self.noteEdit = QPlainTextEdit(self)
        self.noteEdit.setObjectName("assertionNoteEdit")
        self.noteEdit.setAccessibleName(self.tr("Provenance note"))
        self.noteEdit.setMaximumHeight(90)

        help_label = QLabel(self.tr(
            "This records only the claim you enter. It does not infer "
            "presence, ownership, knowledge, or any other meaning from prose."
        ), self)
        help_label.setWordWrap(True)
        self.errorLabel = QLabel(self)
        self.errorLabel.setObjectName("assertionValidationMessage")
        self.errorLabel.setAccessibleName(self.tr("Validation message"))
        self.errorLabel.setWordWrap(True)
        self.errorLabel.hide()

        form = QFormLayout()
        form.addRow(self.tr("&Subject:"), self.subjectCombo)
        form.addRow(self.tr("&Predicate:"), self.predicateCombo)
        form.addRow(self.tr("Object &kind:"), self.objectKindCombo)
        form.addRow(self.tr("&Object:"), self.objectStack)
        form.addRow(self.tr("&Canon state:"), self.canonCombo)
        form.addRow(self.tr("Temporal &scope:"), self.validityAxisCombo)
        form.addRow(self.tr("Valid &from:"), self.validityFromCombo)
        form.addRow(self.tr("Valid &until:"), self.validityUntilCombo)
        form.addRow(self.tr("&Qualifiers:"), self.qualifiersEdit)
        form.addRow(self.tr("Source &anchor:"), self.anchorEdit)
        form.addRow(self.tr("Provenance &note:"), self.noteEdit)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        self.objectKindCombo.currentIndexChanged.connect(
            self.objectStack.setCurrentIndex
        )
        self.validityAxisCombo.currentIndexChanged.connect(
            self._refresh_temporal_controls
        )
        self._refresh_temporal_controls()

        layout = QVBoxLayout(self)
        layout.addWidget(help_label)
        layout.addWidget(self.errorLabel)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    @property
    def assertion(self):
        subject = self.subjectCombo.currentData()
        if self.objectKindCombo.currentData() == "reference":
            reference = self.objectReferenceCombo.currentData()
            term = AssertionTerm.referencing(reference.kind, reference.id)
        else:
            term = AssertionTerm.scalar(
                yaml.safe_load(self.objectValueEdit.text())
            )
        raw_qualifiers = yaml.safe_load(
            self.qualifiersEdit.toPlainText() or "{}"
        )
        return Assertion(
            id=self._assertionId,
            subject=subject,
            predicate=self.predicateCombo.currentText().strip(),
            object=term,
            qualifiers=tuple(
                AssertionQualifier(str(name), item)
                for name, item in raw_qualifiers.items()
            ),
            provenance=AssertionProvenance(
                anchor=self.anchorEdit.text().strip(),
                note=self.noteEdit.toPlainText().strip(),
            ),
            canon_state=self.canonCombo.currentData(),
            validity=self._validity(),
        )

    def _temporal_combo(self, object_name, accessible_name):
        combo = QComboBox(self)
        combo.setObjectName(object_name)
        combo.setAccessibleName(accessible_name)
        return combo

    def _refresh_temporal_controls(self):
        axis = self.validityAxisCombo.currentData()
        for combo in (self.validityFromCombo, self.validityUntilCombo):
            combo.clear()
            combo.addItem(self.tr("Unspecified"), None)
            for label, point in self._temporalChoices:
                if point.axis is axis:
                    combo.addItem(str(label), point)
            combo.setEditable(axis is TemporalAxis.STORY)
            combo.setEnabled(axis is not None)
            if combo.isEditable():
                combo.lineEdit().setPlaceholderText(
                    self.tr("Choose an event/scene or enter ISO-8601 time")
                )

    def _validity(self):
        axis = self.validityAxisCombo.currentData()
        if axis is None:
            return None
        start = self._temporal_point(self.validityFromCombo, axis)
        end = self._temporal_point(self.validityUntilCombo, axis)
        return TemporalInterval(start, end)

    @staticmethod
    def _temporal_point(combo, axis):
        point = combo.currentData()
        if point is not None:
            return point
        text = combo.currentText().strip()
        if not text or (
            combo.currentIndex() == 0 and text == combo.itemText(0)
        ):
            return None
        if axis is not TemporalAxis.STORY:
            raise ValueError(
                "Narrative boundaries must select a manuscript document."
            )
        return TemporalPoint.story_time(text)

    def _validate_and_accept(self):
        if not self.predicateCombo.currentText().strip():
            self._show_error(
                self.tr("Enter a predicate for this assertion."),
                self.predicateCombo,
            )
            return
        if (
            self.objectKindCombo.currentData() == "value"
            and not self.objectValueEdit.text().strip()
        ):
            self._show_error(
                self.tr("Enter a scalar value, or choose Reference."),
                self.objectValueEdit,
            )
            return
        try:
            raw_qualifiers = yaml.safe_load(
                self.qualifiersEdit.toPlainText() or "{}"
            )
            if not isinstance(raw_qualifiers, dict):
                raise TypeError("Qualifiers must be a YAML mapping.")
            self.assertion
        except (TypeError, ValueError, yaml.YAMLError) as error:
            self._show_error(str(error), self.qualifiersEdit)
            return
        self.accept()

    def _show_error(self, message, widget):
        self.errorLabel.setText(
            self.tr("Cannot add assertion: {}").format(str(message))
        )
        self.errorLabel.show()
        widget.setFocus()
