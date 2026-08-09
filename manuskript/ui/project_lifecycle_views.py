"""Narrow view capabilities used by the project lifecycle adapter.

Only :meth:`ProjectLifecycleViews.for_window` knows where these capabilities
live on a ``MainWindow``.  The lifecycle adapter receives grouped widgets and
operations, so opening or closing a project cannot turn into arbitrary access
to the window, its application services, or unrelated plugin state.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Tuple

from manuskript.ui.views.textEditView import textEditView


@dataclass(frozen=True)
class ProjectCommandViews:
    """Actions whose availability follows whether a project is open."""

    closed_only: Tuple[Any, ...]
    open_only: Tuple[Any, ...]
    tools_menu: Any
    global_tool_actions: Callable[[], Tuple[Any, ...]]


@dataclass(frozen=True)
class LoadedSettingsViews:
    """One workspace's controls affected by persisted project settings."""

    view_state: Any
    rebuild_view_menu: Callable[[], None]
    editor: Any
    spellcheck_action: Any
    set_spellcheck: Callable[[bool], None]
    rebuild_dictionary_menu: Callable[[], None]
    set_dictionary: Callable[[], None]
    project_tree: Any
    set_simple_mode: Callable[[], None]
    set_fiction_mode: Callable[[], None]


@dataclass(frozen=True)
class ProjectWorkspaceViews:
    """Capabilities used while a workspace enters or leaves a project."""

    tabs: Any
    set_session_start_word_count: Callable[[int], None]
    set_window_title: Callable[[str], None]
    reset_history: Callable[[], None]
    notify_plugins_opened: Callable[[], None]
    notify_plugins_closing: Callable[[], None]
    show_project: Callable[[], None]
    show_welcome: Callable[[], None]
    update_welcome: Callable[[], None]
    view_state: Any
    restore_workspace_windows: Callable[[], Tuple[Any, ...]]
    connect_project: Callable[[], None]
    disconnect_project: Callable[[], None]
    undo_stack: Any
    editor: Any
    private_text_editors: Callable[[], Tuple[Any, ...]]


@dataclass(frozen=True)
class ProjectDialogViews:
    """The presentation capabilities needed by lifecycle dialogs."""

    parent: Any
    translate: Callable[[str], str]


@dataclass(frozen=True)
class ProjectLifecycleViews:
    """All view-side lifecycle capabilities, grouped by responsibility."""

    commands: ProjectCommandViews
    loaded_settings: LoadedSettingsViews
    workspace: ProjectWorkspaceViews
    dialogs: ProjectDialogViews
    show_status: Callable[[str, int, int], None]

    @classmethod
    def for_window(cls, window):
        """Take an inventory once; do not hand the window to the consumer."""
        plugin_ui = window.pluginUi

        def global_tool_actions():
            if plugin_ui is None:
                return ()
            return tuple(plugin_ui.globalActions)

        def notify_plugins_opened():
            if plugin_ui is not None:
                plugin_ui.project_opened()

        def notify_plugins_closing():
            if plugin_ui is not None:
                plugin_ui.prepare_project_close()

        def set_session_start_word_count(value):
            window.sessionStartWordCount = value

        return cls(
            commands=ProjectCommandViews(
                closed_only=(window.actOpen, window.menuRecents),
                open_only=(
                    window.actSave,
                    window.actSaveAs,
                    window.actGitRevisions,
                    window.actCloseProject,
                    window.menuEdit,
                    window.menuView,
                    window.menuOrganize,
                    window.menuNavigate,
                    window.menuHelp,
                    window.actImport,
                    window.actCompile,
                    window.actSettings,
                ),
                tools_menu=window.menuTools,
                global_tool_actions=global_tool_actions,
            ),
            loaded_settings=LoadedSettingsViews(
                view_state=window.windowState,
                rebuild_view_menu=window.generateViewMenu,
                editor=window.mainEditor,
                spellcheck_action=window.actSpellcheck,
                set_spellcheck=window.toggleSpellcheck,
                rebuild_dictionary_menu=window.updateMenuDict,
                set_dictionary=window.setDictionary,
                project_tree=window.corePanels.project_tree.tree,
                set_simple_mode=window.setViewModeSimple,
                set_fiction_mode=window.setViewModeFiction,
            ),
            workspace=ProjectWorkspaceViews(
                tabs=window.tabMain,
                set_session_start_word_count=(
                    set_session_start_word_count
                ),
                set_window_title=window.setWindowTitle,
                reset_history=window.history.reset,
                notify_plugins_opened=notify_plugins_opened,
                notify_plugins_closing=notify_plugins_closing,
                show_project=window.switchToProject,
                show_welcome=window.switchToWelcome,
                update_welcome=window.welcome.updateValues,
                view_state=window.windowState,
                restore_workspace_windows=window.restoreWorkspaceWindows,
                connect_project=window.makeConnections,
                disconnect_project=window.breakConnections,
                undo_stack=window.undoStack,
                editor=window.mainEditor,
                private_text_editors=partial(
                    window.findChildren,
                    textEditView,
                ),
            ),
            dialogs=ProjectDialogViews(
                # A QWidget parent is the capability dialogs need. Giving
                # them the MainWindow would recreate the service locator.
                parent=window.centralWidget(),
                translate=window.tr,
            ),
            show_status=window.statusPresenter.show,
        )
