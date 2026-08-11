import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class GitRevisionDialog(QDialog):
    """Project-scoped Git history and milestone management."""

    def __init__(
        self,
        project_manager,
        settings,
        coordinator,
        parent=None,
    ):
        super().__init__(parent)
        self.project_manager = project_manager
        self.settings = settings
        self.coordinator = coordinator
        self._backend = None
        self._buildUi()
        self.refresh()

    def _buildUi(self):
        self.setWindowTitle(self.tr("Git Revision History"))
        self.resize(1050, 650)
        layout = QVBoxLayout(self)

        self.lblRepository = QLabel(self)
        self.lblRepository.setWordWrap(True)
        layout.addWidget(self.lblRepository)

        controls = QHBoxLayout()
        self.chkTaggedOnly = QCheckBox(
            self.tr("Tagged milestones only"),
            self,
        )
        self.chkTaggedOnly.setToolTip(self.tr(
            "Hide fine-grained recovery commits and show only "
            "author-selected milestones."
        ))
        self.chkTaggedOnly.setChecked(
            bool(
                self.settings.revisions
                .get("git", {})
                .get("taggedOnly", True)
            )
        )
        self.chkTaggedOnly.toggled.connect(
            self._tagFilterChanged
        )
        controls.addWidget(self.chkTaggedOnly)
        controls.addStretch(1)
        self.btnRefresh = QPushButton(self.tr("Refresh"), self)
        self.btnRefresh.clicked.connect(self.refresh)
        controls.addWidget(self.btnRefresh)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal, self)
        self.history = QTreeWidget(splitter)
        self.history.setRootIsDecorated(False)
        self.history.setAlternatingRowColors(True)
        self.history.setUniformRowHeights(True)
        self.history.setHeaderLabels([
            self.tr("Date"),
            self.tr("Message"),
            self.tr("Tags"),
            self.tr("Commit"),
        ])
        header = self.history.header()
        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents,
        )
        header.setSectionResizeMode(
            3,
            QHeaderView.ResizeToContents,
        )
        self.history.itemSelectionChanged.connect(
            self._showSelectedRevision
        )

        self.details = QPlainTextEdit(splitter)
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QPlainTextEdit.NoWrap)
        splitter.addWidget(self.history)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([600, 450])
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.btnCommit = QPushButton(
            self.tr("Commit current project…"),
            self,
        )
        self.btnCommit.setToolTip(self.tr(
            "Save and commit only this Manuskript project. "
            "Unrelated staged files are not included."
        ))
        self.btnCommit.clicked.connect(self._commit)
        actions.addWidget(self.btnCommit)

        self.btnTag = QPushButton(
            self.tr("Tag as milestone…"),
            self,
        )
        self.btnTag.clicked.connect(self._tag)
        self.btnTag.setEnabled(False)
        actions.addWidget(self.btnTag)

        self.btnRestore = QPushButton(
            self.tr("Restore selected…"),
            self,
        )
        self.btnRestore.clicked.connect(self._restore)
        self.btnRestore.setEnabled(False)
        actions.addWidget(self.btnRestore)
        self.btnStructuralDiff = QPushButton(
            self.tr("Structural diff to current"), self
        )
        self.btnStructuralDiff.setToolTip(self.tr(
            "Compare documents, metadata, references, assertions, and "
            "paragraph structure without restoring files."
        ))
        self.btnStructuralDiff.clicked.connect(self._structuralDiff)
        self.btnStructuralDiff.setEnabled(False)
        actions.addWidget(self.btnStructuralDiff)
        actions.addStretch(1)
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Close,
            parent=self,
        )
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def refresh(self):
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self._backend = self.coordinator.git_backend(
                self.project_manager.currentProject
            )
            status = self._backend.status()
            revisions = self._backend.history(
                tagged_only=self.chkTaggedOnly.isChecked()
            )
            self._showStatus(status)
            self._populateHistory(revisions)
        except Exception as error:
            self._backend = None
            self.history.clear()
            self.details.setPlainText(str(error))
            self.lblRepository.setText(
                self.tr("Git revisions unavailable: {}").format(
                    str(error)
                )
            )
        finally:
            QApplication.restoreOverrideCursor()
        self._updateActionState()

    def _showStatus(self, status):
        branch = status.branch or self.tr("detached HEAD")
        changes = (
            self.tr(
                "{} staged, {} modified, {} untracked, "
                "{} conflicted project files"
            ).format(
                status.staged,
                status.modified,
                status.untracked,
                status.conflicts,
            )
            if status.dirty
            else self.tr("project worktree clean")
        )
        self.lblRepository.setText(
            self.tr("Repository: {} — branch: {} — {}").format(
                self._backend.repository.root,
                branch,
                changes,
            )
        )

    def _populateHistory(self, revisions):
        selected = self._selectedCommit()
        self.history.clear()
        selected_item = None
        for revision in revisions:
            date = datetime.datetime.fromtimestamp(
                revision.timestamp
            ).astimezone().strftime("%Y-%m-%d %H:%M")
            item = QTreeWidgetItem([
                date,
                revision.subject,
                ", ".join(revision.tags),
                revision.short_id,
            ])
            item.setData(0, Qt.UserRole, revision.commit_id)
            item.setToolTip(1, revision.subject)
            if revision.tags:
                font = item.font(1)
                font.setBold(True)
                item.setFont(1, font)
            self.history.addTopLevelItem(item)
            if revision.commit_id == selected:
                selected_item = item

        if selected_item is not None:
            self.history.setCurrentItem(selected_item)
        elif self.history.topLevelItemCount():
            self.history.setCurrentItem(
                self.history.topLevelItem(0)
            )
        elif self.chkTaggedOnly.isChecked():
            self.details.setPlainText(self.tr(
                "No tagged milestones were found. Create a tag on "
                "a meaningful commit, or show all commits."
            ))
        else:
            self.details.setPlainText(
                self.tr("No project commits were found.")
            )

    def _showSelectedRevision(self):
        commit_id = self._selectedCommit()
        self._updateActionState()
        if self._backend is None or commit_id is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.details.setPlainText(
                self._backend.revision_details(commit_id)
            )
        except Exception as error:
            self._showError(error)
        finally:
            QApplication.restoreOverrideCursor()

    def _structuralDiff(self):
        commit_id = self._selectedCommit()
        if commit_id is None:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            current = self.project_manager.captureCanonicalProject()
            report = self.coordinator.structural_diff(
                self.project_manager.currentProject,
                commit_id,
                current,
                self.settings,
            )
            self.details.setPlainText(report.render_text())
        except Exception as error:
            self._showError(error)
        finally:
            QApplication.restoreOverrideCursor()

    def _tagFilterChanged(self, checked):
        git_settings = self.settings.revisions.setdefault("git", {})
        git_settings["taggedOnly"] = bool(checked)
        self.refresh()

    def _commit(self):
        message, accepted = QInputDialog.getMultiLineText(
            self,
            self.tr("Commit current project"),
            self.tr("Commit message:"),
        )
        if not accepted or not message.strip():
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            commit_id = self.project_manager.commitRevision(message)
        except Exception as error:
            self._showError(error)
            return
        finally:
            QApplication.restoreOverrideCursor()

        if commit_id is None:
            QMessageBox.information(
                self,
                self.tr("Nothing to commit"),
                self.tr(
                    "The saved project already matches the current "
                    "Git commit."
                ),
            )
        self.refresh()

    def _tag(self):
        commit_id = self._selectedCommit()
        if commit_id is None:
            return
        name, accepted = QInputDialog.getText(
            self,
            self.tr("Tag revision as a milestone"),
            self.tr("Tag name:"),
        )
        if not accepted or not name.strip():
            return
        try:
            self.coordinator.create_tag(
                self.project_manager.currentProject,
                commit_id,
                name,
            )
        except Exception as error:
            self._showError(error)
            return
        self.refresh()

    def _restore(self):
        commit_id = self._selectedCommit()
        if commit_id is None:
            return
        result = QMessageBox.warning(
            self,
            self.tr("Restore Git revision?"),
            self.tr(
                "Manuskript will save the current project, read the "
                "selected commit into a separate model, validate it, "
                "and then replace the project through its normal save "
                "path.\n\nGit will not modify the worktree. Continue?"
            ),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if result != QMessageBox.Yes:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            restored = self.project_manager.restoreRevision(commit_id)
        except Exception as error:
            self._showError(error)
            return
        finally:
            QApplication.restoreOverrideCursor()
        if restored:
            self.refresh()

    def _selectedCommit(self):
        items = self.history.selectedItems()
        return (
            items[0].data(0, Qt.UserRole)
            if items
            else None
        )

    def _updateActionState(self):
        selected = self._selectedCommit() is not None
        available = self._backend is not None
        self.btnCommit.setEnabled(available)
        self.btnTag.setEnabled(available and selected)
        self.btnRestore.setEnabled(available and selected)
        self.btnStructuralDiff.setEnabled(available and selected)

    def _showError(self, error):
        QMessageBox.critical(
            self,
            self.tr("Git revision error"),
            str(error),
        )
