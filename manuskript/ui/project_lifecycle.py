from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QListWidgetItem, QMessageBox

from manuskript.domain.project import CloseDecision
from manuskript.enums import Outline
from manuskript.ui.listDialog import ListDialog


class ProjectLifecycleView:
    """Adapt project lifecycle events to concrete main-window widgets."""

    def __init__(self, window):
        self.window = window

    @property
    def settings(self):
        return self.window.settingsManager

    @property
    def model_parent(self):
        return self.window

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
            self.window.actCloseProject,
            self.window.menuEdit,
            self.window.menuView,
            self.window.menuOrganize,
            self.window.menuNavigate,
            self.window.menuTools,
            self.window.menuHelp,
            self.window.actImport,
            self.window.actCompile,
            self.window.actSettings,
        ]:
            item.setEnabled(project_open)

    def connect_project(self):
        self.window.makeConnections()

    def apply_loaded_settings(self):
        settings = self.settings
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
        self.window.switchToProject()

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
        self.window.mainEditor.closeAllTabs()

    def disconnect_project(self):
        self.window.breakConnections()

    def project_closed(self):
        self.window.setWindowTitle(self.window.tr("Manuskript"))
        self.window.welcome.updateValues()
        self.window.switchToWelcome()
