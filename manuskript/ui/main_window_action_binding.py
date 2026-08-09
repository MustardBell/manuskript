from functools import partial

from PyQt5.QtWidgets import QActionGroup

from manuskript import functions as F
from manuskript.commands import DocumentCommand, MarkupCommand
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


def activate_markdown_mode(set_mode, mode, _checked=False):
    """Adapt QAction's checked argument to the mode command's contract."""
    set_mode(mode)


class MainWindowActionBinding:
    """Install application-lifetime main-window signal routing once."""

    def __init__(self, window):
        self._window = window
        self.bound = False

    def bind(self):
        if self.bound:
            raise RuntimeError(
                "Main-window actions may only be bound once."
            )
        window = self._window
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
        # Composition is complete. Every connection now retains only its
        # action and destination; keeping the whole window here would turn
        # this one-shot installer into a permanent service locator.
        self._window = None

    def _bind_file_actions(self):
        window = self._window
        for action, slot in [
            (window.actOpen, window.welcome.openFile),
            (window.actSave, window.projectManager.saveDatas),
            (window.actSaveAs, window.welcome.saveAsFile),
            (
                window.actGitRevisions,
                window.workspaceDialogs.show_revision_history,
            ),
            (window.actImport, window.doImport),
            (window.actCompile, window.doCompile),
            (
                window.actCloseProject,
                window.projectManager.closeProject,
            ),
            # Quit means every workspace window, not just this one.
            (window.actQuit, window.quitApplication),
        ]:
            action.triggered.connect(slot)

    def _bind_edit_actions(self):
        window = self._window
        self._install_history_actions()
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
            (window.actLabels, window.workspaceDialogs.show_labels),
            (window.actStatus, window.workspaceDialogs.show_statuses),
            (window.actSettings, window.workspaceDialogs.show_settings),
        ]:
            action.triggered.connect(slot)

    def _install_history_actions(self):
        """Put project history at the top of the Edit menu.

        No shortcut is attached here. A window-level Ctrl+Z is dispatched
        before the focused widget sees the key, which would take undo away
        from whichever text editor is being typed in. The outline views bind
        it themselves, scoped to the widget.
        """
        window = self._window
        stack = getattr(window.projectRuntime, "undoStack", None)
        if stack is None:
            return
        window.actUndo = stack.createUndoAction(
            window, window.tr("Undo")
        )
        window.actRedo = stack.createRedoAction(
            window, window.tr("Redo")
        )
        first = window.menuEdit.actions()[0]
        window.menuEdit.insertAction(first, window.actUndo)
        window.menuEdit.insertAction(first, window.actRedo)
        window.menuEdit.insertSeparator(first)

    def _bind_format_actions(self):
        window = self._window
        for action, command in [
            (window.actHeaderSetextL1, MarkupCommand.HEADING_SETEXT_1),
            (window.actHeaderSetextL2, MarkupCommand.HEADING_SETEXT_2),
            (window.actHeaderAtxL1, MarkupCommand.HEADING_ATX_1),
            (window.actHeaderAtxL2, MarkupCommand.HEADING_ATX_2),
            (window.actHeaderAtxL3, MarkupCommand.HEADING_ATX_3),
            (window.actHeaderAtxL4, MarkupCommand.HEADING_ATX_4),
            (window.actHeaderAtxL5, MarkupCommand.HEADING_ATX_5),
            (window.actHeaderAtxL6, MarkupCommand.HEADING_ATX_6),
            (window.actFormatBold, MarkupCommand.BOLD),
            (window.actFormatItalic, MarkupCommand.ITALIC),
            (window.actFormatUnderline, MarkupCommand.UNDERLINE),
            (window.actFormatStrike, MarkupCommand.STRIKE),
            (window.actFormatVerbatim, MarkupCommand.VERBATIM),
            (
                window.actFormatSuperscript,
                MarkupCommand.SUPERSCRIPT,
            ),
            (window.actFormatSubscript, MarkupCommand.SUBSCRIPT),
            (
                window.actFormatCommentLines,
                MarkupCommand.COMMENT_LINES,
            ),
            (window.actFormatList, MarkupCommand.UNORDERED_LIST),
            (
                window.actFormatOrderedList,
                MarkupCommand.ORDERED_LIST,
            ),
            (
                window.actFormatBlockquote,
                MarkupCommand.BLOCKQUOTE,
            ),
            (
                window.actFormatCommentBlock,
                MarkupCommand.COMMENT_BLOCK,
            ),
            (window.actFormatClear, MarkupCommand.CLEAR_FORMAT),
        ]:
            action.triggered.connect(
                partial(window.markupCommands.dispatch, command)
            )

    def _bind_organize_actions(self):
        window = self._window
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
        window = self._window
        window.actBack.triggered.connect(
            window.navigationController.back
        )
        window.actForward.triggered.connect(
            window.navigationController.forward
        )

    def _bind_view_actions(self):
        window = self._window
        window.generateViewMenu()
        window.mainEditor.activeMarkdownPresentationStateChanged.connect(
            window.attachMarkdownPresentationState
        )
        window.actModeGroup = QActionGroup(window)
        window.actModeSimple.setActionGroup(window.actModeGroup)
        window.actModeFiction.setActionGroup(window.actModeGroup)
        window.actModeSimple.triggered.connect(
            window.setViewModeSimple
        )
        window.actModeFiction.triggered.connect(
            window.setViewModeFiction
        )
        window.actMarkdownModeGroup = QActionGroup(window)
        for action, mode in [
            (
                window.actMarkdownSource,
                MarkdownPresentationMode.SOURCE,
            ),
            (
                window.actMarkdownFormattedSource,
                MarkdownPresentationMode.FORMATTED_SOURCE,
            ),
            (
                window.actMarkdownLivePreview,
                MarkdownPresentationMode.LIVE_PREVIEW,
            ),
            (
                window.actMarkdownReading,
                MarkdownPresentationMode.READING,
            ),
        ]:
            action.setActionGroup(window.actMarkdownModeGroup)
            action.triggered.connect(
                partial(
                    activate_markdown_mode,
                    window.setMarkdownPresentationMode,
                    mode,
                )
            )
        window.menuMarkdownMode.setEnabled(False)

    def _bind_tool_actions(self):
        window = self._window
        for action, slot in [
            (
                window.actToolFrequency,
                window.workspaceDialogs.show_frequency,
            ),
            (window.actToolTargets, window.workspaceDialogs.show_targets),
            (window.actSupport, window.support),
            (window.actLocateLog, window.locateLogFile),
            (window.actAbout, window.workspaceDialogs.show_about),
        ]:
            action.triggered.connect(slot)

    def _bind_permanent_feature_signals(self):
        window = self._window
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
                window.corePanels.project_tree.add_folder.clicked,
                window.corePanels.project_tree.tree.addFolder,
            ),
            (
                window.btnOutlineAddFolder.clicked,
                window.treeOutlineOutline.addFolder,
            ),
            (
                window.corePanels.project_tree.add_text.clicked,
                window.corePanels.project_tree.tree.addText,
            ),
            (
                window.btnOutlineAddText.clicked,
                window.treeOutlineOutline.addText,
            ),
            (
                window.corePanels.project_tree.remove_item.clicked,
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
        # Focus is application-wide, so the window registry follows it
        # once and forwards to whichever workspace gained it. Connecting
        # per window would have every window react to every other
        # window's focus changes.
        window.windowRegistry.watch_focus()
