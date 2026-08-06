"""Everything a project is, independent of any window showing it.

A project outlives the windows that view it: closing one window must not
close the project, and two windows must edit the same models rather than
copies. So the project's own things -- its manager and session, its
models, its settings, its undo history, its revision coordinator -- are
owned here, and a window receives a runtime it did not build.

The models are parented to a QObject this runtime owns, not to a window.
That is the whole point: Qt deletes children with their parent, and a
window closing is not the project ending.
"""

from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QUndoStack

from manuskript.projectManager import ProjectManager
from manuskript.services.project_view_registry import (
    ProjectViewRegistry,
)
from manuskript.services.document_buffers import (
    DocumentBufferRegistry,
)
from manuskript.services.revision_coordinator import (
    ProjectRevisionCoordinator,
)
from manuskript.settingsManager import SettingsManager


class ProjectRuntime(QObject):
    """The project layer: one per open project, shared by its windows."""

    def __init__(
        self,
        settings_manager=None,
        project_history=None,
        revision_coordinator=None,
        active_window_source=None,
        parent=None,
    ):
        super().__init__(parent)
        self.settingsManager = (
            settings_manager
            if settings_manager is not None
            else SettingsManager()
        )
        # Models hang off the runtime, so they survive any window and
        # die only with the project.
        self.modelParent = QObject(self)
        self.modelParent.setObjectName("projectModels")
        # Structure edits are undoable per project, and every window
        # showing the project shares the one history.
        self.undoStack = QUndoStack(self)
        # One live text per document, shared by every view showing it.
        # Project scope for the same reason the models are: a window
        # closing is not a document closing, and the text a second
        # window is still showing must not go with the first.
        self.documentBuffers = DocumentBufferRegistry(self)
        self.revisionCoordinator = (
            revision_coordinator
            if revision_coordinator is not None
            else ProjectRevisionCoordinator()
        )
        # Every window viewing this project, behind one view-shaped
        # object, so the manager keeps talking to a single "view".
        self.views = ProjectViewRegistry(
            active_window_source=active_window_source
        )
        self.projectManager = None
        self._projectHistory = project_history

    def attach(self, view):
        """Register a window's view side, building the manager on the
        first one.

        The manager is deferred because the runtime is composed before
        any window exists; later windows join a project already running.

        No status reporter is taken from the joining window. The manager
        reports through the view registry, which picks a live window per
        call -- a reporter captured here would be the first window's for
        the life of the project, including after it closed.

        The settings and the model parent are handed over here, from what
        this runtime owns. They used to be read back out of the joining
        window, which made the project's own facts reachable only through
        something that displays them.
        """
        self.views.register(view)
        if self.projectManager is None:
            self.projectManager = ProjectManager(
                self.views,
                self.settingsManager,
                self.modelParent,
                document_buffers=self.documentBuffers,
                last_project_store=self._projectHistory,
                revision_coordinator=self.revisionCoordinator,
            )
        return self.projectManager

    def detach(self, view):
        """Drop a window's view side. The project stays open."""
        self.views.unregister(view)

    @property
    def models(self):
        manager = self.projectManager
        return manager.models if manager is not None else None

    @property
    def session(self):
        manager = self.projectManager
        return manager.session if manager is not None else None

    @property
    def currentProject(self):
        manager = self.projectManager
        return manager.currentProject if manager is not None else None

    @property
    def isOpen(self):
        session = self.session
        return bool(session is not None and session.is_open)
