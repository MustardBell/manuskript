"""Create, restore, adopt, and close application workspace windows."""

from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtCore import QCoreApplication, QEvent, QRect
from PyQt5.QtWidgets import QApplication

from manuskript.services.workspace_state import PRIMARY
from manuskript.ui.workspace_surfaces import WorkspaceBuildIntent


def workspace_id(workspace):
    return getattr(workspace, "windowId", PRIMARY)


@dataclass(frozen=True)
class ProjectAdoptionViews:
    """Project-view operations a newly created workspace must catch up."""

    is_open: Callable[[], bool]
    sync_to_state: Callable[[bool], None]
    connect_project: Callable[[], None]
    apply_loaded_settings: Callable[[], None]
    project_opened: Callable[[], None]


@dataclass(frozen=True)
class LegacyWorkspaceMigrationViews:
    """One-way conversion from floating dock intent to real workspaces."""

    floating_surfaces: Callable[[], tuple]
    move_surface: Callable[[str], Any]
    place_workspace: Callable[[Any, tuple], None]
    save_workspace: Callable[[Any], None]


@dataclass(frozen=True)
class WorkspaceWindowViews:
    """Application/window capabilities needed by workspace coordination."""

    current_id: str
    workspaces: Callable[[], tuple]
    identify: Callable[[Any], str]
    settle_native_deletions: Callable[[], None]
    create: Callable[[str, Any], Any]
    close_all: Callable[[], bool]
    state_store: Callable[[], Any]
    intent_for_state: Callable[[Any], Any]
    adoption: ProjectAdoptionViews
    legacy_migration: LegacyWorkspaceMigrationViews

    @classmethod
    def for_window(cls, window):
        registry = window.windowRegistry
        state = window.windowState
        runtime = window.projectRuntime
        lifecycle = window.projectLifecycleView
        services = window.services
        window_type = type(window)

        def create(window_id, build_intent=None):
            created = window_type(
                services,
                window_id=window_id,
                build_intent=build_intent,
            )
            try:
                created.workspaceWindows.adopt_open_project()
                # A transfer destination must not flash its intermediate
                # composition. It becomes visible only after the running
                # project has caught up with the surface it was built for.
                created.show()
                return created
            except Exception:
                # Construction completed and registered this window, but
                # project adoption did not. Closing releases its bindings and
                # leaves an incoming living surface ownerless for the caller
                # to put back where it came from.
                created.close()
                raise

        def place_workspace(workspace, geometry):
            if not geometry or len(geometry) != 4:
                return
            x, y, width, height = (int(value) for value in geometry)
            available = QApplication.desktop().availableGeometry(workspace)
            minimum = workspace.minimumSizeHint().expandedTo(
                workspace.minimumSize()
            )
            width = max(
                minimum.width(), min(width, available.width())
            )
            height = max(
                minimum.height(), min(height, available.height())
            )
            x = max(
                available.left(),
                min(x, available.right() - width + 1),
            )
            y = max(
                available.top(),
                min(y, available.bottom() - height + 1),
            )
            workspace.setGeometry(QRect(x, y, width, height))

        return cls(
            current_id=window.windowId,
            workspaces=lambda: registry.workspace_windows,
            identify=workspace_id,
            settle_native_deletions=lambda: QCoreApplication.sendPostedEvents(
                None, QEvent.DeferredDelete,
            ),
            create=create,
            close_all=registry.close_all,
            state_store=lambda: state.store,
            intent_for_state=lambda saved: WorkspaceBuildIntent.from_saved(
                saved.surfaces,
                saved.active_surface,
                window.panelRegistry,
            ),
            adoption=ProjectAdoptionViews(
                is_open=lambda: runtime.isOpen,
                sync_to_state=lifecycle.sync_to_state,
                connect_project=lifecycle.connect_project,
                apply_loaded_settings=lifecycle.apply_loaded_settings,
                project_opened=lifecycle.project_opened,
            ),
            legacy_migration=LegacyWorkspaceMigrationViews(
                floating_surfaces=(
                    window.windowState.legacy_floating_surfaces
                ),
                # Resolved at call time: this controller is composed before
                # the View menu builds the transfer controller.
                move_surface=lambda surface_id: (
                    window.surfaceTransfer.move_to_new_workspace(surface_id)
                ),
                place_workspace=place_workspace,
                save_workspace=lambda workspace: workspace.windowState.save(),
            ),
        )


class WorkspaceWindowController:
    """Coordinate the set of windows viewing one running project."""

    def __init__(self, views):
        self.views = views
        self._restoration_attempted = False

    def open_ids(self):
        return [
            self.views.identify(workspace)
            for workspace in self.views.workspaces()
        ]

    def next_id(self):
        taken = set(self.open_ids())
        index = 2
        while "window-{}".format(index) in taken:
            index += 1
        return "window-{}".format(index)

    def open(self, window_id=None, _checked=False):
        # QAction.triggered supplies a bool; it is not a workspace id.
        if isinstance(window_id, bool):
            window_id = None
        # A just-closed secondary uses WA_DeleteOnClose. Synchronous callers
        # can ask for another workspace before the event loop has delivered
        # that DeferredDelete; letting it arrive halfway through composition
        # interleaves destruction of one native tree with construction of the
        # next. Establish the native lifetime boundary first.
        self.views.settle_native_deletions()
        return self.views.create(window_id or self.next_id(), None)

    def open_with_intent(self, build_intent, window_id=None):
        """Compose a workspace for declared membership, then reveal it."""

        self.views.settle_native_deletions()
        return self.views.create(
            window_id or self.next_id(), build_intent,
        )

    def adopt_open_project(self):
        adoption = self.views.adoption
        if not adoption.is_open():
            return False
        adoption.sync_to_state(True)
        adoption.connect_project()
        adoption.apply_loaded_settings()
        adoption.project_opened()
        return True

    def quit(self, _checked=False):
        views = self.views
        session = self.open_ids()
        store = views.state_store()
        # A quit invoked from a secondary workspace closes and disposes that
        # workspace before close_all returns, so retain only the two explicit
        # capabilities needed after the close begins.
        if not views.close_all():
            return False
        store.set_open_windows(session)
        return True

    def restore(self):
        if self._restoration_attempted:
            return ()
        if self.views.current_id != PRIMARY:
            return ()
        self._restoration_attempted = True
        reopened = []
        store = self.views.state_store()
        recorded_windows = store.open_windows()
        for window_id in recorded_windows:
            if window_id in self.open_ids():
                continue
            intent = self.views.intent_for_state(store.load(window_id))
            reopened.append(self.open_with_intent(intent, window_id))

        migrated = []
        migration = self.views.legacy_migration
        for layout in migration.floating_surfaces():
            workspace = migration.move_surface(layout.surface_id)
            if workspace is None:
                continue
            migration.place_workspace(workspace, layout.geometry)
            migrated.append(workspace)

        if migrated:
            # Persist the declarative answer immediately.  If the application
            # exits abnormally before a normal quit, the obsolete dock blob
            # must not be the only record of the windows just recovered.
            for workspace in self.views.workspaces():
                migration.save_workspace(workspace)
            store.set_open_windows(self.open_ids())
        reopened.extend(migrated)
        return tuple(reopened)

    def reset_restoration(self, attempted=False):
        """Reset restoration state for a new application session or test."""
        self._restoration_attempted = bool(attempted)

    def dispose(self):
        self.views = None
