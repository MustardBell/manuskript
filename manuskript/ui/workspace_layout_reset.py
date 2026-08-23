"""Restore the application's one canonical first-open workspace."""

import logging

from dataclasses import dataclass
from typing import Any, Callable, Tuple

from manuskript.services.workspace_state import PRIMARY


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkspaceLayoutResetViews:
    """Window operations needed by the application-level reset command."""

    current_workspace: Any
    workspaces: Callable[[], Tuple[Any, ...]]
    identify: Callable[[Any], str]
    surface_host: Callable[[Any], Any]
    flush_pending_edits: Callable[[Any], None]
    close_contributed_ui: Callable[[Any], None]
    open_surface: Callable[[Any, str], Any]
    activate_surface: Callable[[Any, str], bool]
    reconstruct_layout: Callable[[Any], None]
    close_workspace: Callable[[Any], bool]
    remember_session: Callable[[Tuple[str, ...]], None]
    show_status: Callable[[Any, str, int, int], None]
    core_surface_ids: Tuple[str, ...]
    default_surface: str


class WorkspaceLayoutResetController:
    """Reunite core surfaces before restoring first-open presentation.

    A local QMainWindow layout operation cannot produce the first-open
    workspace after a surface has moved to a peer window.  Reset is therefore
    an explicit composition command: it gathers the living core instances in
    the primary workspace, retires the other workspaces, and only then asks
    the primary to rebuild its native dock grid.
    """

    def __init__(self, views):
        self.views = views

    def reset(self, _checked=False):
        views = self.views
        if views is None:
            return False
        workspaces = tuple(views.workspaces())
        if not workspaces:
            return False
        primary = next(
            (
                workspace
                for workspace in workspaces
                if views.identify(workspace) == PRIMARY
            ),
            None,
        )
        if primary is None:
            views.show_status(
                views.current_workspace,
                "The main workspace is not open, so its default layout "
                "cannot be restored.",
                8000,
                3,
            )
            return False

        # No view may disappear with an editor that has not submitted its
        # private state.  Flush every workspace before changing membership.
        try:
            for workspace in workspaces:
                views.flush_pending_edits(workspace)
            for workspace in workspaces:
                views.close_contributed_ui(workspace)
        except Exception:
            LOGGER.exception(
                "Could not prepare workspace UI for a layout reset."
            )
            views.show_status(
                primary,
                "The workspace layout was not reset because pending edits "
                "or contributed UI could not be settled.",
                8000,
                3,
            )
            return False

        target = views.surface_host(primary)
        moved = []
        constructed = []
        try:
            for surface_id in views.core_surface_ids:
                if target.instance(surface_id) is not None:
                    continue
                donor = next(
                    (
                        workspace
                        for workspace in workspaces
                        if workspace is not primary
                        and views.surface_host(workspace).instance(
                            surface_id
                        ) is not None
                    ),
                    None,
                )
                if donor is None:
                    views.open_surface(primary, surface_id)
                    constructed.append(surface_id)
                    continue
                source = views.surface_host(donor)
                instance = source.detach(surface_id)
                if instance is None:
                    raise RuntimeError(
                        "The donor stopped owning {} during reset."
                        .format(surface_id)
                    )
                try:
                    target.attach(instance)
                except Exception:
                    if instance.host is target:
                        target.detach(surface_id)
                    if instance.host is None:
                        source.attach(instance)
                    raise
                moved.append((source, instance))

            if not views.activate_surface(primary, views.default_surface):
                raise RuntimeError(
                    "The default surface could not be activated."
                )
            views.reconstruct_layout(primary)
        except Exception:
            LOGGER.exception(
                "Could not reconstruct the first-open workspace layout."
            )
            for surface_id in reversed(constructed):
                target.close(surface_id)
            for source, instance in reversed(moved):
                if instance.host is target:
                    target.detach(instance.id)
                if instance.host is None:
                    source.attach(instance)
            views.show_status(
                primary,
                "The workspace layout could not be reset; moved surfaces "
                "were restored to their previous windows.",
                8000,
                3,
            )
            return False

        # Close the invoking secondary last. Its WorkspaceLifetime owns this
        # controller, so this method may be disposed while its stack frame is
        # still completing. All operations needed afterwards were captured in
        # the immutable view port above.
        peers = [
            workspace for workspace in workspaces
            if workspace is not primary
            and workspace is not views.current_workspace
        ]
        if (
            views.current_workspace is not primary
            and views.current_workspace in workspaces
        ):
            peers.append(views.current_workspace)
        for workspace in peers:
            if not views.close_workspace(workspace):
                views.show_status(
                    primary,
                    "The core layout was restored, but a secondary "
                    "workspace refused to close.",
                    8000,
                    2,
                )
                return False

        views.remember_session((views.identify(primary),))
        views.show_status(
            primary,
            "Workspace layout reset to the first-open arrangement.",
            5000,
            1,
        )
        return True

    def dispose(self):
        self.views = None
