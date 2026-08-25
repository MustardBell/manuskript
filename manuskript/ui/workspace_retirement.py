"""Preserve living surfaces when one workspace view is retired."""

import logging

from dataclasses import dataclass
from typing import Any, Callable

from manuskript.services.workspace_state import PRIMARY
from manuskript.ui.workspace_surfaces import WorkspaceSurfaceError


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceRetirementViews:
    """The ownership operations needed before a workspace may disappear."""

    current_workspace: Any
    workspaces: Callable[[], tuple]
    identify: Callable[[Any], str]
    surface_host: Callable[[Any], Any]
    show_status: Callable[[str, int, int], None]
    translate: Callable[[str], str]

    @classmethod
    def for_window(cls, window):
        return cls(
            current_workspace=window,
            workspaces=lambda: window.windowRegistry.workspace_windows,
            identify=lambda workspace: workspace.windowId,
            surface_host=lambda workspace: workspace.surfaceHost,
            show_status=window.statusPresenter.show,
            translate=window.tr,
        )


class WorkspaceRetirementController:
    """Move unique living surfaces before their workspace is destroyed.

    Closing a view is not a command to delete the only Editor, Outline, or
    contributed surface in the running project. A surface already present in
    another workspace is merely this window's duplicate view and may end with
    it. A unique instance, however, is transferred to the primary surviving
    workspace without rebuilding its widget or bindings.
    """

    def __init__(self, views):
        self.views = views

    def preserve_unique_surfaces(self):
        views = self.views
        current = views.current_workspace
        peers = tuple(
            workspace
            for workspace in views.workspaces()
            if workspace is not current
        )
        if not peers:
            return True

        destination = next(
            (
                workspace for workspace in peers
                if views.identify(workspace) == PRIMARY
            ),
            peers[0],
        )
        source_host = views.surface_host(current)
        destination_host = views.surface_host(destination)
        previous_surface = source_host.current()
        moved = []

        try:
            for instance in tuple(source_host.instances.values()):
                if any(
                    views.surface_host(peer).contains(instance.id)
                    for peer in peers
                ):
                    continue
                detached = source_host.detach(instance.id)
                if detached is None:
                    raise WorkspaceSurfaceError(
                        "The retiring workspace lost {} before transfer."
                        .format(instance.id)
                    )
                moved.append(detached)
                destination_host.attach(detached)
            return True
        except Exception:
            LOGGER.exception(
                "Could not preserve surfaces while retiring workspace %s.",
                views.identify(current),
            )
            for instance in reversed(moved):
                if instance.host is destination_host:
                    destination_host.detach(instance.id)
                if instance.host is None:
                    source_host.attach(instance)
            if previous_surface and source_host.contains(previous_surface):
                source_host.activate(previous_surface)
            views.show_status(
                views.translate(
                    "This workspace could not close because one of its "
                    "writing surfaces could not be preserved."
                ),
                8000,
                3,
            )
            return False

    def dispose(self):
        self.views = None
