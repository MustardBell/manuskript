"""Move a living workspace surface without rebuilding its view state."""

import logging

from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtWidgets import QMenu

from manuskript.ui.workspace_surfaces import (
    WorkspaceBuildIntent,
    WorkspaceSurfaceError,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SurfaceTransferViews:
    """The narrow window operations needed by a surface move."""

    host: Any
    menu: Any
    translate: Callable[[str], str]
    project_active: Callable[[], bool]
    flush_pending_edits: Callable[[], None]
    create_workspace: Callable[[WorkspaceBuildIntent], Any]
    close_workspace: Callable[[Any], None]
    workspace_host: Callable[[Any], Any]
    show_status: Callable[[str, int, int], None]

    @classmethod
    def for_window(cls, window, anchor=None):
        menu = QMenu(
            window.tr("Move &Surface to New Window"), window,
        )
        menu.setObjectName("menuMoveSurfaceToNewWindow")
        menu.menuAction().setStatusTip(window.tr(
            "Move one writing surface, with its current view state, to a "
            "new workspace window"
        ))
        window.menuView.insertMenu(anchor, menu)
        return cls(
            host=window.surfaceHost,
            menu=menu,
            translate=window.tr,
            project_active=lambda: window.projectRuntime.isOpen,
            flush_pending_edits=(
                window.projectLifecycleView.flush_pending_edits
            ),
            create_workspace=(
                window.workspaceWindows.open_with_intent
            ),
            close_workspace=lambda workspace: workspace.close(),
            workspace_host=lambda workspace: workspace.surfaceHost,
            show_status=window.statusPresenter.show,
        )


class SurfaceTransferController:
    """Transfer one surface to a workspace composed specifically for it."""

    def __init__(self, views):
        self.views = views
        self.views.menu.aboutToShow.connect(self.build_menu)

    def build_menu(self):
        menu = self.views.menu
        menu.clear()
        if not self.views.project_active():
            self._disabled_action("Open a project to move its surfaces")
            return

        instances = tuple(self.views.host.instances.values())
        if not instances:
            self._disabled_action("This workspace has no surface to move")
            return

        can_move = len(instances) > 1
        for instance in sorted(instances, key=self._sort_key):
            title = self.views.translate(instance.descriptor.title)
            action = menu.addAction(title.replace("&", "&&"))
            action.setData(instance.id)
            if can_move:
                action.setStatusTip(self.views.translate(
                    "Move {} to a new workspace window"
                ).format(title))
                action.triggered.connect(
                    lambda checked=False, surface_id=instance.id: (
                        self.move_to_new_window(surface_id, checked)
                    )
                )
            else:
                action.setEnabled(False)
                action.setStatusTip(self.views.translate(
                    "A workspace must keep at least one surface"
                ))

    @staticmethod
    def _sort_key(instance):
        navigator = instance.descriptor.navigator
        return (
            navigator.order if navigator is not None else 10_000,
            instance.descriptor.title.casefold(),
            instance.id,
        )

    def _disabled_action(self, text):
        action = self.views.menu.addAction(self.views.translate(text))
        action.setEnabled(False)
        return action

    def move_to_new_window(self, surface_id, _checked=False):
        """Move one living instance, or leave the source exactly usable."""

        views = self.views
        host = views.host
        instance = host.instance(surface_id)
        if instance is None or not views.project_active():
            return None
        if len(host.instances) <= 1:
            views.show_status(
                views.translate(
                    "A workspace must keep at least one surface."
                ),
                5000,
                2,
            )
            return None

        previous_surface = host.current()
        destination = None
        try:
            # Private editors are not represented by shared document
            # buffers. Submit them while their source bindings still exist.
            views.flush_pending_edits()
            detached = host.detach(surface_id)
            if detached is None:
                raise WorkspaceSurfaceError(
                    "The source no longer owns the requested surface."
                )
            instance = detached
            destination = views.create_workspace(
                WorkspaceBuildIntent.for_transfer(instance)
            )
            if destination is None:
                raise WorkspaceSurfaceError(
                    "The destination workspace was not created."
                )
            destination_host = views.workspace_host(destination)
            if instance.host is not destination_host:
                raise WorkspaceSurfaceError(
                    "The destination did not adopt the living surface."
                )
            return instance
        except Exception:
            LOGGER.exception(
                "Could not move workspace surface %s to a new window.",
                surface_id,
            )
            if destination is not None:
                try:
                    views.close_workspace(destination)
                except Exception:
                    LOGGER.exception(
                        "Could not close the failed surface destination."
                    )
            self._rollback(instance, previous_surface)
            views.show_status(
                views.translate(
                    "The surface could not be moved; it was restored to "
                    "this workspace."
                ),
                8000,
                3,
            )
            return None

    def _rollback(self, instance, previous_surface):
        """Recover an instance from either no owner or a partial owner."""

        host = self.views.host
        if instance is None:
            return
        owner = instance.host
        if owner is not None and owner is not host:
            owner.detach(instance.id)
        if instance.host is None:
            host.attach(instance)
        if previous_surface and host.contains(previous_surface):
            host.activate(previous_surface)

    def dispose(self):
        views = self.views
        if views is None:
            return
        try:
            views.menu.aboutToShow.disconnect(self.build_menu)
        except (RuntimeError, TypeError):
            pass
        views.menu.clear()
        self.views = None
