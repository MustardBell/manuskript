"""Revision-settings presentation and commands for one settings dialog."""

import os
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtWidgets import QMessageBox

from manuskript.domain.revisions import RevisionBackendKind
from manuskript.services.git_revisions import GitCommandRunner


@dataclass(frozen=True)
class RevisionSettingsViews:
    """Only the controls used by the revision settings feature."""

    parent: object
    keep: object
    backend: object
    smart_remove: object
    internal_warning: object
    git_options: object
    git_auto_commit: object
    git_tagged_only: object
    manage_history: object
    initialize_repository: object
    status: object
    ten_minutes: object
    hour: object
    day: object
    month: object
    eternity: object

    @classmethod
    def for_dialog(cls, dialog):
        return cls(
            parent=dialog,
            keep=dialog.chkRevisionsKeep,
            backend=dialog.cmbRevisionBackend,
            smart_remove=dialog.chkRevisionRemove,
            internal_warning=dialog.label_revisionDeprecation,
            git_options=dialog.grpGitRevisionOptions,
            git_auto_commit=dialog.chkGitAutoCommit,
            git_tagged_only=dialog.chkGitTaggedOnly,
            manage_history=dialog.btnManageGitRevisions,
            initialize_repository=dialog.btnInitGitRepository,
            status=dialog.lblRevisionStatus,
            ten_minutes=dialog.spnRevisions10Mn,
            hour=dialog.spnRevisionsHour,
            day=dialog.spnRevisionsDay,
            month=dialog.spnRevisionsMonth,
            eternity=dialog.spnRevisionsEternity,
        )


class RevisionSettingsController:
    """Own revision settings state, availability, and UI commands."""

    def __init__(
        self,
        views: RevisionSettingsViews,
        settings,
        *,
        current_project: Callable[[], str],
        show_history: Callable[[object], None],
        availability: Callable[[], object],
        translate: Callable[[str], str],
        runner_factory=GitCommandRunner,
    ):
        self.views = views
        self.settings = settings
        self.current_project = current_project
        self.show_history = show_history
        self.availability = availability
        self.translate = translate
        self.runner_factory = runner_factory

    def install(self):
        """Populate controls, then bind them after the initial values exist."""
        self._load()
        for signal in (
            self.views.keep.stateChanged,
            self.views.backend.currentIndexChanged,
            self.views.smart_remove.toggled,
            self.views.git_auto_commit.toggled,
            self.views.git_tagged_only.toggled,
            self.views.ten_minutes.valueChanged,
            self.views.hour.valueChanged,
            self.views.day.valueChanged,
            self.views.month.valueChanged,
            self.views.eternity.valueChanged,
        ):
            signal.connect(self.save)
        self.views.manage_history.clicked.connect(self._show_history)
        self.views.initialize_repository.clicked.connect(
            self.initialize_git_repository
        )
        self.update()

    def _load(self):
        options = self.settings.revisions
        views = self.views
        views.keep.setChecked(options["keep"])
        views.backend.clear()
        views.backend.addItem(
            self.translate("Git project history"),
            RevisionBackendKind.GIT.value,
        )
        views.backend.addItem(
            self.translate("Internal snapshots (legacy, unstable)"),
            RevisionBackendKind.INTERNAL.value,
        )
        backend_index = views.backend.findData(
            options.get("backend", RevisionBackendKind.GIT.value)
        )
        views.backend.setCurrentIndex(max(0, backend_index))
        views.smart_remove.setChecked(options["smartremove"])
        git_options = options.get("git") or {}
        views.git_auto_commit.setChecked(
            bool(git_options.get("autoCommit", False))
        )
        views.git_tagged_only.setChecked(
            bool(git_options.get("taggedOnly", True))
        )
        rules = options["rules"]
        views.ten_minutes.setValue(int(60 / rules[10 * 60]))
        views.hour.setValue(int(60 * 10 / rules[60 * 60]))
        views.day.setValue(int(60 * 60 / rules[60 * 60 * 24]))
        views.month.setValue(
            int(60 * 60 * 24 / rules[60 * 60 * 24 * 30])
        )
        views.eternity.setValue(
            int(60 * 60 * 24 * 7 / rules[None])
        )

    def save(self, *_args):
        views = self.views
        options = self.settings.revisions
        options["keep"] = views.keep.isChecked()
        options["backend"] = views.backend.currentData()
        options["smartremove"] = views.smart_remove.isChecked()
        git_options = options.setdefault("git", {})
        git_options["autoCommit"] = views.git_auto_commit.isChecked()
        git_options["taggedOnly"] = views.git_tagged_only.isChecked()
        options["rules"][10 * 60] = 60 / views.ten_minutes.value()
        options["rules"][60 * 60] = 60 * 10 / views.hour.value()
        options["rules"][60 * 60 * 24] = 60 * 60 / views.day.value()
        options["rules"][60 * 60 * 24 * 30] = (
            60 * 60 * 24 / views.month.value()
        )
        options["rules"][None] = (
            60 * 60 * 24 * 7 / views.eternity.value()
        )
        self.update()

    def update(self):
        views = self.views
        enabled = views.keep.isChecked()
        backend = views.backend.currentData()
        internal = backend == RevisionBackendKind.INTERNAL.value
        git = backend == RevisionBackendKind.GIT.value
        availability = self.availability()

        views.keep.setEnabled(True)
        views.backend.setEnabled(enabled)
        views.smart_remove.setVisible(internal)
        views.smart_remove.setEnabled(enabled and internal)
        views.internal_warning.setVisible(internal)
        views.git_options.setVisible(git)
        views.git_options.setEnabled(
            enabled and git and availability.git_installed
        )
        views.manage_history.setEnabled(
            enabled and git and availability.usable
        )
        views.initialize_repository.setVisible(
            git and availability.needs_repository
        )
        views.initialize_repository.setEnabled(
            enabled and bool(self.current_project())
        )
        views.status.setVisible(git and not availability.usable)
        views.status.setText(self.status_message(availability))

    def status_message(self, availability):
        if not availability.git_installed:
            return self.translate(
                "Git is not installed, so Git history cannot record "
                "anything. Install Git, or turn revisions off, or switch "
                "to the legacy internal snapshots."
            )
        if availability.needs_repository:
            if not self.current_project():
                return self.translate(
                    "Open a project to see whether it is kept in a Git "
                    "repository."
                )
            return self.translate(
                "This project is not inside a Git repository, so no "
                "history is being recorded. Create one to start keeping "
                "revisions."
            )
        return ""

    def _show_history(self, _checked=False):
        self.show_history(self.views.parent)

    def initialize_git_repository(self, _checked=False):
        project = self.current_project()
        if not project:
            return
        directory = os.path.dirname(os.path.abspath(project)) or os.curdir
        confirmed = QMessageBox.question(
            self.views.parent,
            self.translate("Create a Git repository?"),
            self.translate(
                "<p>Manuskript will run <code>git init</code> in:</p>"
                "<p><code>{}</code></p>"
                "<p>Nothing is committed and no existing file is changed. "
                "You can remove the repository later by deleting its "
                "<code>.git</code> directory.</p>"
            ).format(directory),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirmed != QMessageBox.Yes:
            return
        runner = self.runner_factory()
        if not runner.available:
            self.update()
            return
        result = runner.execute(("-C", directory, "init"))
        if result.return_code:
            QMessageBox.warning(
                self.views.parent,
                self.translate("Could not create the repository"),
                result.stderr.decode("utf-8", errors="replace").strip()
                or self.translate("git init failed."),
            )
        self.update()
