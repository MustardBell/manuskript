from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QListWidgetItem, QMessageBox

from manuskript.domain.project import CloseDecision
from manuskript.enums import Outline
from manuskript.ui.listDialog import ListDialog
from manuskript.ui.views.textEditView import textEditView


class ProjectLifecycleView:
    """Adapt project lifecycle events to concrete main-window widgets."""

    def __init__(self, window):
        self.window = window

    @property
    def settings(self):
        return self.window.projectRuntime.settingsManager

    @property
    def model_parent(self):
        """The runtime's model parent, never the window.

        Qt deletes children with their parent, and a window closing is
        not the project ending -- models parented to a window would go
        with the first one to close.
        """
        return self.window.projectRuntime.modelParent

    def translate(self, text):
        return self.window.tr(text)

    def project_name(self):
        return self.window.projectName()

    def install_models(self, models):
        models.install_on(self.window)

    def change_models(self):
        return [
            self.window.mdlFlatData,
            self.window.mdlOutline,
            self.window.mdlCharacter,
            self.window.mdlPlots,
            self.window.mdlWorld,
            self.window.mdlStatus,
            self.window.mdlLabels,
        ]

    def sync_to_state(self, project_open):
        for item in [self.window.actOpen, self.window.menuRecents]:
            item.setEnabled(not project_open)
        for item in [
            self.window.actSave,
            self.window.actSaveAs,
            self.window.actGitRevisions,
            self.window.actCloseProject,
            self.window.menuEdit,
            self.window.menuView,
            self.window.menuOrganize,
            self.window.menuNavigate,
            self.window.menuHelp,
            self.window.actImport,
            self.window.actCompile,
            self.window.actSettings,
        ]:
            item.setEnabled(project_open)
        for action in self.window.menuTools.actions():
            if (
                self.window.pluginUi is not None
                and action in self.window.pluginUi.globalActions
            ):
                action.setEnabled(True)
            else:
                action.setEnabled(project_open)
        self.window.menuTools.setEnabled(True)

    def connect_project(self):
        self.window.makeConnections()

    def apply_loaded_settings(self):
        settings = self.settings
        # This window's own documents first: two windows on one project
        # are two places to be reading, and both restoring the project's
        # single list would make them the same place. A window with none
        # recorded falls back to that list, which is what every window
        # did before layouts were per window.
        if not self.window.windowState.restore_documents():
            if settings.openIndexes and settings.openIndexes != [""]:
                self.window.mainEditor.tabSplitter.restoreOpenIndexes(
                    settings.openIndexes
                )
        self.window.generateViewMenu()
        self.window.mainEditor.sldCorkSizeFactor.setValue(
            settings.corkSizeFactor
        )
        self.window.actSpellcheck.setChecked(settings.spellcheck)
        self.window.toggleSpellcheck(settings.spellcheck)
        self.window.updateMenuDict()
        self.window.setDictionary()

        icon_size = settings.viewSettings["Tree"]["iconSize"]
        self.window.treeRedacOutline.setIconSize(
            QSize(icon_size, icon_size)
        )
        self.window.mainEditor.setFolderView(settings.folderView)
        self.window.mainEditor.updateFolderViewButtons(
            settings.folderView
        )
        self.window.mainEditor.tabSplitter.updateStyleSheet()
        self.window.tabMain.setCurrentIndex(settings.lastTab)
        self.window.mainEditor.updateCorkBackground()
        if settings.viewMode == "simple":
            self.window.setViewModeSimple()
        else:
            self.window.setViewModeFiction()

    def project_opened(self):
        settings = self.settings
        self.window.tabMain.currentChanged.emit(settings.lastTab)
        word_count = self.window.mdlOutline.rootItem.data(
            Outline.wordCount
        )
        self.window.sessionStartWordCount = (
            int(word_count) if word_count != "" else 0
        )
        self.window.setWindowTitle(
            self.window.projectName()
            + " - "
            + self.window.tr("Manuskript")
        )
        self.window.history.reset()
        if self.window.pluginUi is not None:
            self.window.pluginUi.project_opened()
        self.window.switchToProject()
        # The window's own arrangement is current again, so anything
        # remembered from the last close is stale.
        self.window.windowState.forget_captured_layout()
        # Only now is there a project for extra windows to show; a
        # workspace window without one is just a welcome screen.
        self.window.restoreWorkspaceWindows()

    def confirm_unsaved_changes(self):
        message = QMessageBox(
            QMessageBox.Question,
            self.window.tr("Save project?"),
            "<p><b>"
            + self.window.tr(
                'Save changes to project "{}" before closing?'
            ).format(self.window.projectName())
            + "</b></p>"
            + "<p>"
            + self.window.tr(
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
            self.window.tr("Files not saved"),
            self.window.tr(
                "The following files were not saved and appear "
                "to be open in another program"
            ),
            files,
        )

    def show_load_failures(self, files):
        self._show_file_failures(
            self.window.tr("Files not loaded"),
            self.window.tr(
                "The following files were not loaded and appear "
                "to be open in another program"
            ),
            files,
        )

    def _show_file_failures(self, title, message, files):
        dialog = ListDialog(self.window)
        dialog.setModal(True)
        dialog.setWindowTitle(title)
        dialog.label.setText(message)
        for filename in files:
            QListWidgetItem(filename, dialog.listWidget)
        dialog.open()

    def prepare_close(self):
        # Before anything is torn down: this window's documents and the
        # arrangement of its panels are only knowable while it still
        # has them.
        self.window.windowState.capture_layout()
        if self.window.pluginUi is not None:
            self.window.pluginUi.prepare_project_close()
        # Structure history belongs to one project. Undoing a deletion from
        # the previous manuscript into a newly opened one would reinsert
        # items that never belonged to it.
        undo_stack = getattr(self.window, "undoStack", None)
        if undo_stack is not None:
            undo_stack.clear()
        self.window.mainEditor.close()
        self.window.mainEditor.closeAllTabs()

    def flush_pending_edits(self):
        """Submit every model-backed text editor before a revision action."""
        for editor in self.window.findChildren(textEditView):
            editor.submit()

    def prepare_model_replacement(self):
        """Release editor widgets before their models are replaced."""
        self.prepare_close()

    def capture_project_state(self):
        """Copy project-scoped view state into persisted settings."""
        self.settings.lastTab = self.window.tabMain.currentIndex()
        self.settings.openIndexes = (
            self.window.mainEditor.tabSplitter.openIndexes()
        )

    def disconnect_project(self):
        self.window.breakConnections()

    def project_closed(self):
        self.window.setWindowTitle(self.window.tr("Manuskript"))
        self.window.welcome.updateValues()
        self.window.switchToWelcome()
