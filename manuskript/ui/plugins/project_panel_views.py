"""Explicit workspace and project capabilities for plugin project panels."""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PluginProjectData:
    """Dynamic access to the project currently owned by a runtime.

    Models are providers rather than captured values because opening another
    manuscript replaces the complete model graph while this workspace and its
    plugin UI remain alive.
    """

    current_file: Callable[[], str]
    plugin_data: Callable[[], Any]
    mark_changed: Callable[[], None]
    is_open: Callable[[], bool]
    show_status: Callable[[str, int, int], None]
    story_services: Callable[[], Any]

    @classmethod
    def for_window(cls, window):
        """Resolve replaceable project state only when it is requested."""

        def plugin_data():
            models = window.projectRuntime.models
            return models.plugin_data

        def is_open():
            manager = getattr(window, "projectManager", None)
            return bool(manager is not None and manager.session.is_open)

        def mark_changed():
            return window.projectManager.startTimerNoChanges()

        def show_status(message, duration=5000, importance=1):
            return window.statusPresenter.show(
                message,
                duration,
                importance,
            )

        return cls(
            current_file=lambda: window.currentProject or "",
            plugin_data=plugin_data,
            mark_changed=mark_changed,
            is_open=is_open,
            show_status=show_status,
            story_services=lambda: window.projectManager,
        )


@dataclass(frozen=True)
class ProjectPanelViews:
    """The fixed view capabilities used by one workspace's panel host."""

    panel_registry: Any
    panel_host: Any
    create_plugins_menu: Callable[[], Any]
    translate: Callable[[str], str]
    dialog_parent: Any
    project: PluginProjectData

    @classmethod
    def for_window(cls, window, project=None):
        """Inventory capabilities once; do not hand over MainWindow."""

        def create_plugins_menu():
            return window.menuTools.addMenu(window.tr("Plugins"))

        return cls(
            panel_registry=window.panelRegistry,
            panel_host=window.panelHost,
            create_plugins_menu=create_plugins_menu,
            translate=window.tr,
            dialog_parent=window.centralWidget() or window,
            project=project or PluginProjectData.for_window(window),
        )
