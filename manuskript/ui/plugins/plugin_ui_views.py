"""Explicit composition port for one workspace's plugin user interface."""

from dataclasses import dataclass
from typing import Any, Callable

from manuskript.panels.core import EDITOR
from manuskript.ui.plugins.editor_workspace_views import (
    EditorWorkspaceViews,
)
from manuskript.ui.plugins.project_panel_views import (
    PluginProjectData,
    ProjectPanelViews,
)


@dataclass(frozen=True)
class PluginUiViews:
    """The complete authority of a workspace-level plugin UI host."""

    object_parent: Any
    dialog_parent: Any
    tools_menu: Any
    translate: Callable[[str], str]
    show_status: Callable[[str, int, int], None]
    editor_host: Callable[[], Any]
    export_context: Callable[[], Any]
    refresh_card_styles: Callable[[], None]
    project_panels: ProjectPanelViews
    editor_workspaces: EditorWorkspaceViews

    @classmethod
    def for_window(cls, window):
        project = PluginProjectData.for_window(window)
        # Plugins may open project dialogs while the welcome central widget
        # is detached.  The workspace remains their stable Qt owner.
        parent = window

        def refresh_card_styles():
            service = getattr(window, "cardStyles", None)
            if service is not None:
                service.refresh()

        def editor_host():
            instance = window.surfaceHost.instance(EDITOR)
            return instance.widget.editor if instance is not None else None

        return cls(
            object_parent=parent,
            dialog_parent=parent,
            tools_menu=window.menuTools,
            translate=window.tr,
            show_status=project.show_status,
            editor_host=editor_host,
            export_context=window.workspaceTransfers.export_context,
            refresh_card_styles=refresh_card_styles,
            project_panels=ProjectPanelViews.for_window(
                window,
                project=project,
            ),
            editor_workspaces=EditorWorkspaceViews.for_window(
                window,
                project=project,
            ),
        )
