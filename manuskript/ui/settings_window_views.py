"""Explicit capabilities used by the application settings window.

The settings UI changes several independent parts of a workspace.  Keeping
those operations grouped here lets the widget do that work without retaining
the ``MainWindow`` service catalog or discovering unrelated state through it.
Project values are deliberately exposed as providers because a workspace can
open another project while the application is running.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from PyQt5.QtWidgets import QWidget

from manuskript.ui.editors.tabSplitter import tabSplitter
from manuskript.ui.views.outlineView import outlineView
from manuskript.ui.views.textEditView import textEditView


@dataclass(frozen=True)
class SettingsProjectViews:
    """Project and revision capabilities used by settings."""

    models: Callable[[], Any]
    current_file: Callable[[], Optional[str]]
    reconfigure_autosave: Callable[[], None]
    show_revision_history: Callable[[Any], None]


@dataclass(frozen=True)
class SettingsStartupViews:
    """Persistent startup choices, independent of the welcome widget."""

    auto_load_values: Callable[[], Tuple[bool, str]]
    set_auto_load: Callable[[bool], None]
    last_accessed_directory: Callable[[], str]


@dataclass(frozen=True)
class SettingsAppearanceViews:
    """Workspace presentation operations affected by appearance settings."""

    set_font: Callable[[Any], None]
    set_view_setting: Callable[[str, str, str], None]
    rebuild_view_menu: Callable[[], None]
    outlines: Callable[[], Tuple[Any, ...]]
    project_tree: Any
    update_stats: Callable[[], None]
    update_cork_view: Callable[[], None]
    update_cork_background: Callable[[], None]


@dataclass(frozen=True)
class SettingsEditorViews:
    """Editor widgets that must apply changed typography immediately."""

    text_editors: Callable[[], Tuple[Any, ...]]
    tab_splitters: Callable[[], Tuple[Any, ...]]
    folder_text_views: Callable[[], Tuple[Any, ...]]


@dataclass(frozen=True)
class SettingsWindowViews:
    """Complete, narrow authority granted to one settings window."""

    parent: Any
    project: SettingsProjectViews
    startup: SettingsStartupViews
    appearance: SettingsAppearanceViews
    editors: SettingsEditorViews

    @classmethod
    def for_window(cls, window, parent=None):
        runtime = window.projectRuntime
        manager = window.projectManager
        history = window.projectHistory
        editor = window.corePanels.editor.editor
        project_tree = window.corePanels.project_tree.tree

        return cls(
            parent=(
                parent
                if parent is not None
                else window
            ),
            project=SettingsProjectViews(
                models=lambda: runtime.models,
                current_file=lambda: runtime.currentProject,
                reconfigure_autosave=manager.reconfigureAutosave,
                show_revision_history=(
                    window.workspaceDialogs.show_revision_history
                ),
            ),
            startup=SettingsStartupViews(
                auto_load_values=history.auto_load_values,
                set_auto_load=history.set_auto_load,
                last_accessed_directory=(
                    history.last_accessed_directory
                ),
            ),
            appearance=SettingsAppearanceViews(
                set_font=window.setFont,
                set_view_setting=(
                    window.viewConfigurationController.set_view_setting
                ),
                rebuild_view_menu=window.viewSettingsMenu.rebuild,
                outlines=lambda: tuple(window.findChildren(outlineView)),
                project_tree=project_tree,
                update_stats=editor.updateStats,
                update_cork_view=editor.updateCorkView,
                update_cork_background=editor.updateCorkBackground,
            ),
            editors=SettingsEditorViews(
                text_editors=lambda: tuple(
                    window.findChildren(textEditView)
                ),
                tab_splitters=lambda: tuple(
                    window.findChildren(tabSplitter)
                ),
                folder_text_views=lambda: tuple(
                    window.findChildren(
                        QWidget,
                        "editorWidgetFolderText",
                    )
                ),
            ),
        )
