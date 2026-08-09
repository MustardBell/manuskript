import os

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QListWidgetItem, QMessageBox

from manuskript import timing
from manuskript.domain.project import CloseDecision
from manuskript.enums import Outline
from manuskript.ui.listDialog import ListDialog


class ProjectLifecycleView:
    """Adapt project lifecycle events to explicit workspace capabilities."""

    def __init__(self, runtime, views):
        self.runtime = runtime
        self.views = views

    @property
    def settings(self):
        """The runtime-owned settings used to configure this workspace."""
        return self.runtime.settingsManager

    def translate(self, text):
        return self.views.dialogs.translate(text)

    def show_status(self, message, duration=5000, importance=1):
        """Put a remark in this window's own status bar.

        Asked for by name rather than handed over as a bound method, so
        the manager holds no reference to any one window's presenter and
        a closed window cannot be reported into.
        """
        self.views.show_status(message, duration, importance)

    def project_name(self):
        name = os.path.basename(self.runtime.currentProject or "")
        return name[:-4] if name.endswith(".msk") else name

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self.runtime.models

    def sync_to_state(self, project_open):
        commands = self.views.commands
        for item in commands.closed_only:
            item.setEnabled(not project_open)
        for item in commands.open_only:
            item.setEnabled(project_open)
        global_actions = commands.global_tool_actions()
        for action in commands.tools_menu.actions():
            if action in global_actions:
                action.setEnabled(True)
            else:
                action.setEnabled(project_open)
        commands.tools_menu.setEnabled(True)

    def connect_project(self):
        self.views.workspace.connect_project()

    def apply_loaded_settings(self):
        settings = self.settings
        views = self.views.loaded_settings
        # This window's own view of the project first -- which documents
        # were open and which tab it was on. Two windows are two places
        # to be working, and both taking the project's single answer
        # would make them the same place. What this window never recorded
        # falls back to the project's.
        with timing.span("settings.reopen_documents"):
            views.view_state.restore_view_state(
                documents=settings.openIndexes,
                main_tab=settings.lastTab,
            )
        with timing.span("settings.view_menu"):
            views.rebuild_view_menu()
        views.editor.sldCorkSizeFactor.setValue(
            settings.corkSizeFactor
        )
        with timing.span("settings.spellcheck"):
            views.spellcheck_action.setChecked(settings.spellcheck)
            views.set_spellcheck(settings.spellcheck)
        with timing.span("settings.dictionary"):
            views.rebuild_dictionary_menu()
            views.set_dictionary()

        icon_size = settings.viewSettings["Tree"]["iconSize"]
        views.project_tree.setIconSize(
            QSize(icon_size, icon_size)
        )
        with timing.span("settings.folder_view"):
            views.editor.setFolderView(settings.folderView)
            views.editor.updateFolderViewButtons(
                settings.folderView
            )
            views.editor.tabSplitter.updateStyleSheet()
            views.editor.updateCorkBackground()
        with timing.span("settings.view_mode"):
            if settings.viewMode == "simple":
                views.set_simple_mode()
            else:
                views.set_fiction_mode()

    def project_opened(self):
        workspace = self.views.workspace
        # The tab this window actually landed on, which is its own where
        # it recorded one and the project's otherwise.
        workspace.tabs.currentChanged.emit(
            workspace.tabs.currentIndex()
        )
        word_count = self.models.outline.rootItem.data(
            Outline.wordCount
        )
        workspace.writing_session.reset(
            int(word_count) if word_count != "" else 0
        )
        workspace.set_window_title(
            self.project_name()
            + " - "
            + self.translate("Manuskript")
        )
        workspace.reset_history()
        workspace.notify_plugins_opened()
        workspace.show_project()
        # The window's own arrangement is current again, so anything
        # remembered from the last close is stale.
        workspace.view_state.forget_captured_layout()
        # Only now is there a project for extra windows to show; a
        # workspace window without one is just a welcome screen.
        workspace.restore_workspace_windows()

    def confirm_unsaved_changes(self):
        message = QMessageBox(
            QMessageBox.Question,
            self.translate("Save project?"),
            "<p><b>"
            + self.translate(
                'Save changes to project "{}" before closing?'
            ).format(self.project_name())
            + "</b></p>"
            + "<p>"
            + self.translate(
                "Your changes will be lost if you don't save them."
            )
            + "</p>",
            QMessageBox.Save
            | QMessageBox.Discard
            | QMessageBox.Cancel,
        )
        result = message.exec()
        if result == QMessageBox.Save:
            return CloseDecision.SAVE
        if result == QMessageBox.Discard:
            return CloseDecision.DISCARD
        return CloseDecision.CANCEL

    def show_save_failures(self, files):
        self._show_file_failures(
            self.translate("Files not saved"),
            self.translate(
                "The following files were not saved and appear "
                "to be open in another program"
            ),
            files,
        )

    def show_load_failures(self, files):
        self._show_file_failures(
            self.translate("Files not loaded"),
            self.translate(
                "The following files were not loaded and appear "
                "to be open in another program"
            ),
            files,
        )

    def _show_file_failures(self, title, message, files):
        dialog = ListDialog(self.views.dialogs.parent)
        dialog.setModal(True)
        dialog.setWindowTitle(title)
        dialog.label.setText(message)
        for filename in files:
            QListWidgetItem(filename, dialog.listWidget)
        dialog.open()

    def prepare_close(self):
        # Before anything is torn down: this window's view of the project
        # and the arrangement of its panels are only knowable while it
        # still has them.
        workspace = self.views.workspace
        workspace.view_state.capture_layout()
        workspace.notify_plugins_closing()
        # Structure history belongs to one project. Undoing a deletion from
        # the previous manuscript into a newly opened one would reinsert
        # items that never belonged to it.
        undo_stack = workspace.undo_stack
        if undo_stack is not None:
            undo_stack.clear()
        workspace.editor.close()
        workspace.editor.closeAllTabs()

    def flush_pending_edits(self):
        """Write out this window's own unsubmitted text.

        Only this window's editors. The shared buffers, where the text of
        a document open in two windows lives, belong to the project and
        are flushed by it -- once, whatever the window count. What is left
        here is the text no shared buffer stands for: a character's notes,
        a multiple selection, anything an editor holds privately.
        """
        for editor in self.views.workspace.private_text_editors():
            editor.submit()

    def prepare_model_replacement(self):
        """Release editor widgets before their models are replaced."""
        self.prepare_close()

    def capture_project_state(self):
        """Copy project-scoped view state into persisted settings."""
        workspace = self.views.workspace
        self.settings.lastTab = workspace.tabs.currentIndex()
        self.settings.openIndexes = (
            workspace.editor.tabSplitter.openIndexes()
        )

    def disconnect_project(self):
        self.views.workspace.disconnect_project()

    def project_closed(self):
        workspace = self.views.workspace
        workspace.set_window_title(self.translate("Manuskript"))
        workspace.update_welcome()
        workspace.show_welcome()
