"""Explicit workspace capabilities for plugin editor workspaces."""

from dataclasses import dataclass
from typing import Any, Callable

from manuskript.panels.core import EDITOR
from manuskript.ui.plugins.project_panel_views import PluginProjectData


@dataclass(frozen=True)
class EditorWorkspaceViews:
    """One workspace's plugin-editor surface and dynamic project data."""

    object_parent: Any
    editor_host: Callable[[], Any]
    translate: Callable[[str], str]
    project: PluginProjectData

    @classmethod
    def for_window(cls, window, project=None):
        def editor_host():
            instance = window.surfaceHost.instance(EDITOR)
            return instance.widget.editor if instance is not None else None

        return cls(
            object_parent=window,
            editor_host=editor_host,
            translate=window.tr,
            project=project or PluginProjectData.for_window(window),
        )
