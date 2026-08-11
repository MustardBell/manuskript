"""Copy-only Project Format upgrade workflow and forensic report."""

import logging
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


LOGGER = logging.getLogger(__name__)


class ProjectUpgradeDialog(QDialog):
    def __init__(self, project_manager, migration_service, parent=None):
        super().__init__(parent)
        self.projectManager = project_manager
        self.migrationService = migration_service
        self._upgradedFile = ""
        self.setWindowTitle(self.tr("Upgrade Project Format"))
        self.setMinimumSize(720, 520)

        intro = QLabel(self.tr(
            "Create and validate a separate Project Format 2 copy. "
            "The open source project is saved first and never replaced."
        ), self)
        intro.setWordWrap(True)
        self.destinationEdit = QLineEdit(self)
        self.destinationEdit.setObjectName("upgradeDestination")
        self.destinationEdit.setAccessibleName(
            self.tr("Upgrade destination")
        )
        self.destinationEdit.setText(self._suggested_destination())
        destination_label = QLabel(self.tr("&Destination:"), self)
        destination_label.setBuddy(self.destinationEdit)
        self.browseButton = QPushButton(self.tr("&Browse…"), self)
        self.browseButton.clicked.connect(self._browse)

        destination = QHBoxLayout()
        destination.addWidget(destination_label)
        destination.addWidget(self.destinationEdit, 1)
        destination.addWidget(self.browseButton)

        self.messageLabel = QLabel(self)
        self.messageLabel.setObjectName("upgradeMessage")
        self.messageLabel.setAccessibleName(self.tr("Upgrade status"))
        self.messageLabel.setWordWrap(True)
        self.reportEdit = QPlainTextEdit(self)
        self.reportEdit.setObjectName("upgradeReport")
        self.reportEdit.setAccessibleName(self.tr("Migration report"))
        self.reportEdit.setReadOnly(True)
        self.reportEdit.setPlaceholderText(self.tr(
            "The forensic migration report will appear here."
        ))

        actions = QHBoxLayout()
        self.upgradeButton = QPushButton(self.tr("&Upgrade copy"), self)
        self.upgradeButton.clicked.connect(self._upgrade)
        self.openButton = QPushButton(self.tr("&Open upgraded copy"), self)
        self.openButton.clicked.connect(self._open_upgraded)
        self.openButton.setEnabled(False)
        actions.addWidget(self.upgradeButton)
        actions.addWidget(self.openButton)
        actions.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close, parent=self)
        close.rejected.connect(self.reject)
        actions.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(destination)
        layout.addWidget(self.messageLabel)
        layout.addWidget(self.reportEdit, 1)
        layout.addLayout(actions)
        self._update_availability()

    def _suggested_destination(self):
        source = str(self.projectManager.currentProject or "")
        stem, extension = os.path.splitext(source)
        return stem + "-format-2" + (extension or ".msk")

    def _update_availability(self):
        project = self.projectManager.storage.canonical_project
        available = bool(project is not None and project.format_version == 1)
        self.upgradeButton.setEnabled(available)
        self.destinationEdit.setEnabled(available)
        self.browseButton.setEnabled(available)
        if not available:
            self.messageLabel.setText(self.tr(
                "Only an open Project Format 1 project needs this upgrade."
            ))

    def _browse(self):
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            self.tr("Choose Project Format 2 copy"),
            self.destinationEdit.text(),
            self.tr("Manuskript project (*.msk);;All files (*)"),
        )
        if selected:
            self.destinationEdit.setText(selected)

    def _upgrade(self):
        destination = self.destinationEdit.text().strip()
        if not destination:
            self._show_error(self.tr("Choose a destination for the copy."))
            self.destinationEdit.setFocus()
            return False
        self.upgradeButton.setEnabled(False)
        try:
            if not self.projectManager.saveDatas():
                self._show_error(self.tr(
                    "The current project was not saved; no copy was created."
                ))
                return False
            report = self.migrationService.upgrade_copy(
                self.projectManager.currentProject, destination
            )
        except Exception as error:
            LOGGER.exception("Project Format upgrade failed.")
            self._show_error(str(error))
            return False
        finally:
            self._update_availability()
        self._upgradedFile = destination
        self.reportEdit.setPlainText(report.render_text())
        self.messageLabel.setText(self.tr(
            "The validated copy was created. Review the report before opening it."
        ))
        self.openButton.setEnabled(True)
        return True

    def _open_upgraded(self):
        if not self._upgradedFile:
            return False
        source_file = self.projectManager.currentProject
        if not self.projectManager.closeProject():
            return False
        opened = self.projectManager.loadProject(self._upgradedFile)
        if opened:
            self.accept()
            return True
        reopened_source = bool(
            source_file and self.projectManager.loadProject(source_file)
        )
        self._show_error(
            self.tr(
                "The upgraded copy could not be opened. "
                "The original project was reopened."
            )
            if reopened_source else self.tr(
                "The upgraded copy could not be opened. "
                "The original project could not be reopened either."
            )
        )
        return False

    def _show_error(self, message):
        detail = self.tr(
            "Upgrade could not be completed: {}".format(str(message))
        )
        self.messageLabel.setText(detail)
        # Validation failures can be long. Keep the complete, selectable
        # explanation in the report area instead of confining it to one label.
        self.reportEdit.setPlainText(detail)
        self.reportEdit.setFocus(Qt.OtherFocusReason)
