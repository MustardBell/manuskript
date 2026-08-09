"""Explicit workspace capabilities for plugin editor workspaces."""

from dataclasses import dataclass
from typing import Any, Callable

from manuskript.ui.plugins.project_panel_views import PluginProjectData


@dataclass(frozen=True)
class EditorWorkspaceViews:
    """One workspace's plugin-editor surface and dynamic project data."""

    editor_host: Any
    translate: Callable[[str], str]
    project: PluginProjectData

    @classmethod
    def for_window(cls, window, project=None):
        return cls(
            editor_host=window.mainEditor,
            translate=window.tr,
            project=project or PluginProjectData.for_window(window),
        )
