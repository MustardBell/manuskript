from functools import partial

from PyQt5.QtWidgets import QActionGroup

from manuskript import functions as F
from manuskript.commands import DocumentCommand, MarkupCommand
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


def activate_markdown_mode(set_mode, mode, _checked=False):
    """Adapt QAction's checked argument to the mode command's contract."""
    set_mode(mode)


def activate_without_checked(callback, _checked=False):
    """Adapt QAction's checked argument to an argument-free command."""
    callback()


class MainWindowActionBinding:
    """Install application-lifetime main-window signal routing once."""

    def __init__(self, window):
        self._window = window
        self._connections = SignalConnectionRegistry()
        self.bound = False

    def _connect(self, signal, slot, connection_type=None):
        self._connections.connect_weak(signal, slot, connection_type)

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

    def dispose(self):
        """Release every signal installed for this workspace window."""
        self._connections.disconnect_all()

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
            (window.actImport, window.workspaceTransfers.show_import),
            (window.actCompile, window.workspaceTransfers.show_export),
            (
                window.actUpgradeProjectFormat,
                window.workspaceDialogs.show_upgrade,
            ),
            (
                window.actCloseProject,
                window.projectManager.closeProject,
            ),
            # Quit means every workspace window, not just this one.
            (window.actQuit, window.workspaceWindows.quit),
        ]:
            self._connect(action.triggered, slot)

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
            self._connect(
                action.triggered,
                partial(window.documentCommands.dispatch, command)
            )
        for action, slot in [
            (window.actSearch, window.workspaceSearch.show),
            (window.actLabels, window.workspaceDialogs.show_labels),
            (window.actStatus, window.workspaceDialogs.show_statuses),
            (window.actSettings, window.workspaceDialogs.show_settings),
        ]:
            self._connect(action.triggered, slot)

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
            self._connect(
                action.triggered,
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
            self._connect(
                action.triggered,
                partial(window.documentCommands.dispatch, command)
            )

    def _bind_navigation_actions(self):
        window = self._window
        self._connect(
            window.actBack.triggered,
            window.navigationController.back
        )
        self._connect(
            window.actForward.triggered,
            window.navigationController.forward
        )

    def _bind_view_actions(self):
        window = self._window
        window.viewSettingsMenu.rebuild()
        self._connect(
            window.mainEditor.activeMarkdownPresentationStateChanged,
            window.markdownMenu.attach,
        )
        window.actModeGroup = QActionGroup(window)
        window.actModeSimple.setActionGroup(window.actModeGroup)
        window.actModeFiction.setActionGroup(window.actModeGroup)
        self._connect(
            window.actModeSimple.triggered,
            partial(
                activate_without_checked,
                window.viewConfigurationController.set_simple,
            )
        )
        self._connect(
            window.actModeFiction.triggered,
            partial(
                activate_without_checked,
                window.viewConfigurationController.set_fiction,
            )
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
                window.actMarkdownCleanEditing,
                MarkdownPresentationMode.CLEAN_EDITING,
            ),
            (
                window.actMarkdownReading,
                MarkdownPresentationMode.READING,
            ),
        ]:
            action.setActionGroup(window.actMarkdownModeGroup)
            self._connect(
                action.triggered,
                partial(
                    activate_markdown_mode,
                    window.markdownMenu.set_mode,
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
            (window.actSupport, window.workspaceSupport.open_support),
            (window.actLocateLog, window.workspaceSupport.locate_log),
            (window.actAbout, window.workspaceDialogs.show_about),
        ]:
            self._connect(action.triggered, slot)

    def _bind_permanent_feature_signals(self):
        window = self._window
        for signal, slot in [
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
                window.corePanels.project_tree.tree.delete,
            ),
            (
                window.btnOutlineRemoveItem.clicked,
                window.treeOutlineOutline.delete,
            ),
        ]:
            self._connect(signal, slot, F.AUC)

        self._connect(
            window.tabMain.currentChanged,
            window.toolbar.setCurrentGroup
        )
        self._connect(
            window.tabMain.currentChanged,
            window.workspaceSelection.tab_changed,
        )
        self._connect(
            window.actNewWindow.triggered,
            window.workspaceWindows.open,
        )
        # Focus is application-wide, so the window registry follows it
        # once and forwards to whichever workspace gained it. Connecting
        # per window would have every window react to every other
        # window's focus changes.
        window.windowRegistry.watch_focus()
