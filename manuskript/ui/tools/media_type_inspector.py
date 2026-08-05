"""What formats exist, who cares about them, and what the user changed.

This is a developer tool on purpose. Overriding a media type asserts a fact
about the bytes somebody else's code emits: get it wrong and exports produce
well-formed content under the wrong name, silently. That belongs behind a
developer menu rather than in Settings.

Declaring a format is the safe half and the useful one. A plugin cannot know
every format, so the user can name one it has never heard of, and then either
choose what stands in for it or leave it unassigned until something arrives
that can produce it.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from manuskript.media_types import (
    CORE,
    PROMISES,
    USER,
    MediaType,
    MediaTypeError,
)


#: Column order in the table.
COLUMN_ID = 0
COLUMN_LABEL = 1
COLUMN_DECLARED = 2
COLUMN_PROMISES = 3
COLUMN_FALLBACK = 4

#: Shown where a format has no producer and nothing stands in for it.
UNASSIGNED = "—"


def promise_summary(registry, media_id):
    """Who promised what about a format, in a readable line."""
    promises = registry.promises(media_id)
    parts = []
    for kind in PROMISES:
        origins = promises.get(kind, ())
        if origins:
            parts.append("{} {}".format(
                ", ".join(origins),
                kind[:-1] if kind.endswith("s") else kind,
            ))
    return " · ".join(parts)


class MediaTypeDialog(QDialog):
    """Name a format Manuskript has never heard of."""

    def __init__(self, registry, parent=None, media_type=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Declare a media type"))
        self._registry = registry

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self.identifierEdit = QLineEdit(self)
        self.identifierEdit.setPlaceholderText(
            "application/x-fictionbook+xml"
        )
        form.addRow(self.tr("Identifier"), self.identifierEdit)

        self.labelEdit = QLineEdit(self)
        self.labelEdit.setPlaceholderText(self.tr("FictionBook 2"))
        form.addRow(self.tr("Name"), self.labelEdit)

        self.baseCombo = QComboBox(self)
        self.baseCombo.addItem(self.tr("Nothing — it stands alone"), "")
        for known in registry.known():
            self.baseCombo.addItem(known.label or known.id, known.id)
        form.addRow(self.tr("A kind of"), self.baseCombo)

        self.textualBox = QCheckBox(
            self.tr("Pages can be written in this format"),
            self,
        )
        self.textualBox.setChecked(True)
        self.textualBox.setToolTip(self.tr(
            "Clear this for a destination assembled from something else, "
            "the way ePub is assembled from HTML."
        ))
        form.addRow("", self.textualBox)

        if media_type is not None:
            self.identifierEdit.setText(media_type.id)
            self.identifierEdit.setReadOnly(True)
            self.labelEdit.setText(media_type.label)
            self.textualBox.setChecked(media_type.textual)
            index = self.baseCombo.findData(media_type.base)
            self.baseCombo.setCurrentIndex(max(0, index))

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def mediaType(self):
        """The declaration, or None when it cannot be built."""
        try:
            return MediaType(
                self.identifierEdit.text().strip(),
                label=self.labelEdit.text().strip(),
                base=self.baseCombo.currentData() or "",
                textual=self.textualBox.isChecked(),
            )
        except MediaTypeError:
            return None

    def validationError(self):
        """Why this declaration cannot be used, or '' when it can.

        Separate from :meth:`accept` so the rule can be checked without
        raising a modal dialog to check it.
        """
        media_type = self.mediaType()
        if media_type is None:
            return self.tr("A media type needs an identifier.")
        if not media_type.label:
            return self.tr(
                "A media type needs a name, or the list shows a blank row."
            )
        return ""

    def accept(self):
        problem = self.validationError()
        if problem:
            QMessageBox.warning(
                self,
                self.tr("Incomplete media type"),
                problem,
            )
            return
        super().accept()


class MediaTypeInspector(QDialog):
    """The whole vocabulary, and the two things the user may change."""

    def __init__(self, registry, preferences, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Media types"))
        self.registry = registry
        self.preferences = preferences
        self.resize(860, 460)

        layout = QVBoxLayout(self)

        self.introLabel = QLabel(
            self.tr(
                "Every format Manuskript, its plugins, or you have named. "
                "Declaring one is safe. Overriding one asserts what another "
                "plugin's output really is, so it is easy to get wrong."
            ),
            self,
        )
        self.introLabel.setWordWrap(True)
        layout.addWidget(self.introLabel)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels([
            self.tr("Identifier"),
            self.tr("Name"),
            self.tr("Declared by"),
            self.tr("Promises"),
            self.tr("Stands in with"),
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            COLUMN_ID, QHeaderView.Stretch
        )
        layout.addWidget(self.table)

        buttonRow = QHBoxLayout()
        self.declareButton = QPushButton(self.tr("Declare…"), self)
        self.declareButton.clicked.connect(self.declare)
        buttonRow.addWidget(self.declareButton)

        self.fallbackButton = QPushButton(
            self.tr("Choose what stands in…"), self
        )
        self.fallbackButton.clicked.connect(self.assign_fallback)
        buttonRow.addWidget(self.fallbackButton)

        self.overrideButton = QPushButton(self.tr("Override…"), self)
        self.overrideButton.setToolTip(self.tr(
            "Remap this identifier to another, for a plugin that named its "
            "output wrongly."
        ))
        self.overrideButton.clicked.connect(self.assign_override)
        buttonRow.addWidget(self.overrideButton)

        buttonRow.addStretch(1)
        self.closeButton = QPushButton(self.tr("Close"), self)
        self.closeButton.clicked.connect(self.accept)
        buttonRow.addWidget(self.closeButton)
        layout.addLayout(buttonRow)

        self.refresh()

    # ------------------------------------------------------------ the table

    def refresh(self):
        selected = self.selected_id()
        self.table.setRowCount(0)
        for media_type in self.registry.known():
            self._add_row(media_type)
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(
            COLUMN_ID, QHeaderView.Stretch
        )
        if selected:
            self.select(selected)

    def _add_row(self, media_type):
        row = self.table.rowCount()
        self.table.insertRow(row)
        override = self.registry.override(media_type.id)

        identifier = QTableWidgetItem(override or media_type.id)
        identifier.setData(Qt.UserRole, media_type.id)
        if override:
            # Bold says there is an override; the tooltip says what it
            # replaced, so a change made months ago is still explicable.
            font = QFont(identifier.font())
            font.setBold(True)
            identifier.setFont(font)
            identifier.setToolTip(
                self.tr("Declared as {}, overridden by you").format(
                    media_type.id
                )
            )
        self.table.setItem(row, COLUMN_ID, identifier)

        self.table.setItem(
            row,
            COLUMN_LABEL,
            QTableWidgetItem(
                media_type.label
                or self.tr("(not named yet)")
            ),
        )
        self.table.setItem(
            row,
            COLUMN_DECLARED,
            QTableWidgetItem(
                ", ".join(self.registry.declared_by(media_type.id))
            ),
        )
        self.table.setItem(
            row,
            COLUMN_PROMISES,
            QTableWidgetItem(
                promise_summary(self.registry, media_type.id)
            ),
        )

        chain = self._chain(media_type.id)
        stands_in = QTableWidgetItem(
            self.registry.label(chain[1]) if len(chain) > 1 else UNASSIGNED
        )
        if len(chain) > 1:
            stands_in.setToolTip(" → ".join(chain))
        self.table.setItem(row, COLUMN_FALLBACK, stands_in)

    def _chain(self, media_id):
        try:
            return self.registry.fallback_chain(media_id)
        except MediaTypeError:
            return (media_id,)

    def selected_id(self):
        item = self.table.item(self.table.currentRow(), COLUMN_ID)
        return item.data(Qt.UserRole) if item is not None else ""

    def select(self, media_id):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COLUMN_ID)
            if item is not None and item.data(Qt.UserRole) == media_id:
                self.table.setCurrentCell(row, COLUMN_ID)
                return

    # ------------------------------------------------------------- actions

    def declare(self):
        dialog = MediaTypeDialog(self.registry, self)
        if dialog.exec() != QDialog.Accepted:
            return
        media_type = dialog.mediaType()
        try:
            self.registry.declare(media_type, USER)
        except MediaTypeError as error:
            QMessageBox.warning(
                self, self.tr("Cannot declare that"), str(error)
            )
            return
        self.preferences.remember_declaration(media_type)
        self.refresh()
        self.select(media_type.id)

    def assign_fallback(self):
        media_id = self.selected_id()
        if not media_id:
            return
        target = self._ask_for_target(
            media_id,
            self.tr("What should stand in for {}?"),
            self.registry.fallback(media_id),
        )
        if target is None:
            return
        try:
            self.registry.assign_fallback(media_id, target)
        except MediaTypeError as error:
            QMessageBox.warning(
                self, self.tr("Cannot use that"), str(error)
            )
            return
        self.preferences.remember_fallback(media_id, target)
        self.refresh()
        self.select(media_id)

    def assign_override(self):
        media_id = self.selected_id()
        if not media_id:
            return
        target = self._ask_for_target(
            media_id,
            self.tr("What is {} really?"),
            self.registry.override(media_id),
        )
        if target is None:
            return
        if target and not self._confirm_override(media_id, target):
            return
        try:
            self.registry.assign_override(media_id, target)
        except MediaTypeError as error:
            QMessageBox.warning(
                self, self.tr("Cannot use that"), str(error)
            )
            return
        self.preferences.remember_override(media_id, target)
        self.refresh()
        self.select(media_id)

    def _confirm_override(self, media_id, target):
        """Name who is affected before the user commits.

        This is what declaring an interest was for: everyone who said they
        care about a format is on record, so the consequences of remapping
        it can be stated rather than discovered.
        """
        affected = [
            origin
            for origin in self.registry.declared_by(media_id)
            if origin not in (CORE, USER)
        ]
        message = self.tr(
            "Remap {} to {}?\n\nThis says what that format really is. If "
            "it is wrong, exports will be produced under the wrong name "
            "without failing."
        ).format(media_id, target)
        if affected:
            message += "\n\n" + self.tr(
                "Declared by: {}"
            ).format(", ".join(affected))
        return QMessageBox.question(
            self,
            self.tr("Override a media type"),
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _ask_for_target(self, media_id, question, current):
        """Pick another declared format, or nothing. None means cancelled."""
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("Media types"))
        layout = QVBoxLayout(dialog)
        prompt = QLabel(question.format(media_id), dialog)
        prompt.setWordWrap(True)
        layout.addWidget(prompt)

        combo = QComboBox(dialog)
        combo.addItem(self.tr("Nothing — leave it unassigned"), "")
        for known in self.registry.known():
            if known.id == media_id:
                continue
            combo.addItem(known.label or known.id, known.id)
        index = combo.findData(current) if current else 0
        combo.setCurrentIndex(index if index >= 0 else 0)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        return combo.currentData() or ""
