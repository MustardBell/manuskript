from functools import partial

from PyQt5.QtWidgets import QActionGroup, qApp

from manuskript import functions as F
from manuskript.commands import DocumentCommand


class MainWindowActionBinding:
    """Install application-lifetime main-window signal routing once."""

    def __init__(self, window):
        self.window = window
        self.bound = False

    def bind(self):
        if self.bound:
            raise RuntimeError(
                "Main-window actions may only be bound once."
            )
        window = self.window
        window.projectManager.syncUiToState()

        self._bind_file_actions()
        self._bind_edit_actions()
        self._bind_format_actions()
        self._bind_organize_actions()
        self._bind_navigation_actions()
        self._bind_view_actions()
        self._bind_tool_actions()
        self._bind_permanent_feature_signals()
        self.bound = True

    def _bind_file_actions(self):
        window = self.window
        for action, slot in [
            (window.actOpen, window.welcome.openFile),
            (window.actSave, window.projectManager.saveDatas),
            (window.actSaveAs, window.welcome.saveAsFile),
            (window.actImport, window.doImport),
            (window.actCompile, window.doCompile),
            (
                window.actCloseProject,
                window.projectManager.closeProject,
            ),
            (window.actQuit, window.close),
        ]:
            action.triggered.connect(slot)

    def _bind_edit_actions(self):
        window = self.window
        for action, command in [
            (window.actCopy, DocumentCommand.COPY),
            (window.actCut, DocumentCommand.CUT),
            (window.actPaste, DocumentCommand.PASTE),
            (window.actRename, DocumentCommand.RENAME),
            (window.actDuplicate, DocumentCommand.DUPLICATE),
            (window.actDelete, DocumentCommand.DELETE),
        ]:
            action.triggered.connect(
                partial(window.documentCommands.dispatch, command)
            )
        for action, slot in [
            (window.actSearch, window.doSearch),
            (window.actLabels, window.settingsLabel),
            (window.actStatus, window.settingsStatus),
            (window.actSettings, window.settingsWindow),
        ]:
            action.triggered.connect(slot)

    def _bind_format_actions(self):
        window = self.window
        for action, slot in [
            (window.actHeaderSetextL1, window.formatSetext1),
            (window.actHeaderSetextL2, window.formatSetext2),
            (window.actHeaderAtxL1, window.formatAtx1),
            (window.actHeaderAtxL2, window.formatAtx2),
            (window.actHeaderAtxL3, window.formatAtx3),
            (window.actHeaderAtxL4, window.formatAtx4),
            (window.actHeaderAtxL5, window.formatAtx5),
            (window.actHeaderAtxL6, window.formatAtx6),
            (window.actFormatBold, window.formatBold),
            (window.actFormatItalic, window.formatItalic),
            (window.actFormatUnderline, window.formatUnderline),
            (window.actFormatStrike, window.formatStrike),
            (window.actFormatVerbatim, window.formatVerbatim),
            (
                window.actFormatSuperscript,
                window.formatSuperscript,
            ),
            (window.actFormatSubscript, window.formatSubscript),
            (
                window.actFormatCommentLines,
                window.formatCommentLines,
            ),
            (window.actFormatList, window.formatList),
            (
                window.actFormatOrderedList,
                window.formatOrderedList,
            ),
            (
                window.actFormatBlockquote,
                window.formatBlockquote,
            ),
            (
                window.actFormatCommentBlock,
                window.formatCommentBlock,
            ),
            (window.actFormatClear, window.formatClear),
        ]:
            action.triggered.connect(slot)

    def _bind_organize_actions(self):
        window = self.window
        for action, command in [
            (window.actMoveUp, DocumentCommand.MOVE_UP),
            (window.actMoveDown, DocumentCommand.MOVE_DOWN),
            (window.actSplitDialog, DocumentCommand.SPLIT_DIALOG),
            (window.actSplitCursor, DocumentCommand.SPLIT_CURSOR),
            (window.actMerge, DocumentCommand.MERGE),
        ]:
            action.triggered.connect(
                partial(window.documentCommands.dispatch, command)
            )

    def _bind_navigation_actions(self):
        window = self.window
        window.actBack.triggered.connect(
            window.navigationController.back
        )
        window.actForward.triggered.connect(
            window.navigationController.forward
        )

    def _bind_view_actions(self):
        window = self.window
        window.generateViewMenu()
        window.actModeGroup = QActionGroup(window)
        window.actModeSimple.setActionGroup(window.actModeGroup)
        window.actModeFiction.setActionGroup(window.actModeGroup)
        window.actModeSimple.triggered.connect(
            window.setViewModeSimple
        )
        window.actModeFiction.triggered.connect(
            window.setViewModeFiction
        )

    def _bind_tool_actions(self):
        window = self.window
        for action, slot in [
            (window.actToolFrequency, window.frequencyAnalyzer),
            (window.actToolTargets, window.sessionTargets),
            (window.actSupport, window.support),
            (window.actLocateLog, window.locateLogFile),
            (window.actAbout, window.about),
        ]:
            action.triggered.connect(slot)

    def _bind_permanent_feature_signals(self):
        window = self.window
        for signal, slot in [
            (
                window.txtPersosFilter.textChanged,
                window.lstCharacters.setFilter,
            ),
            (
                window.lstCharacters.itemSelectionChanged,
                window.characterController.handle_selection_changed,
            ),
            (
                window.txtPlotFilter.textChanged,
                window.lstPlots.setFilter,
            ),
            (
                window.lstPlots.currentItemChanged,
                window.plotController.handle_plot_selection_changed,
            ),
            (
                window.btnRedacAddFolder.clicked,
                window.treeRedacOutline.addFolder,
            ),
            (
                window.btnOutlineAddFolder.clicked,
                window.treeOutlineOutline.addFolder,
            ),
            (
                window.btnRedacAddText.clicked,
                window.treeRedacOutline.addText,
            ),
            (
                window.btnOutlineAddText.clicked,
                window.treeOutlineOutline.addText,
            ),
            (
                window.btnRedacRemoveItem.clicked,
                window.outlineRemoveItemsRedac,
            ),
            (
                window.btnOutlineRemoveItem.clicked,
                window.outlineRemoveItemsOutline,
            ),
        ]:
            signal.connect(slot, F.AUC)

        window.tabMain.currentChanged.connect(
            window.toolbar.setCurrentGroup
        )
        window.tabMain.currentChanged.connect(window.tabMainChanged)
        qApp.focusChanged.connect(window.focusChanged)
