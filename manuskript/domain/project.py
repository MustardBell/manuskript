from enum import Enum


class InvalidProjectStateTransition(RuntimeError):
    """Raised when a project operation is invalid for the current state."""


class ProjectState(Enum):
    CLOSED = "closed"
    CLEAN = "clean"
    DIRTY = "dirty"


class ProjectSession:
    """Track the current project path and its finite lifecycle state."""

    _allowed_transitions = {
        ProjectState.CLOSED: {ProjectState.CLEAN},
        ProjectState.CLEAN: {ProjectState.CLOSED, ProjectState.DIRTY},
        ProjectState.DIRTY: {ProjectState.CLOSED, ProjectState.CLEAN},
    }

    def __init__(self):
        self._path = None
        self._state = ProjectState.CLOSED

    @property
    def path(self):
        return self._path

    @property
    def state(self):
        return self._state

    @property
    def is_open(self):
        return self._state is not ProjectState.CLOSED

    @property
    def is_dirty(self):
        return self._state is ProjectState.DIRTY

    def _transition_to(self, state):
        if state is self._state:
            return
        if state not in self._allowed_transitions[self._state]:
            raise InvalidProjectStateTransition(
                "Cannot transition project from {} to {}.".format(
                    self._state.value, state.value
                )
            )
        self._state = state

    def open(self, path):
        if self.is_open:
            raise InvalidProjectStateTransition(
                "Cannot open a project while another project is still open."
            )
        if not path:
            raise ValueError("A project path is required.")
        self._transition_to(ProjectState.CLEAN)
        self._path = path

    def rename(self, path):
        if not self.is_open:
            raise InvalidProjectStateTransition(
                "Cannot rename a project when no project is open."
            )
        if not path:
            raise ValueError("A project path is required.")
        self._path = path

    def mark_dirty(self):
        if not self.is_open:
            raise InvalidProjectStateTransition(
                "Cannot mark a project dirty when no project is open."
            )
        self._transition_to(ProjectState.DIRTY)

    def mark_clean(self):
        if not self.is_open:
            raise InvalidProjectStateTransition(
                "Cannot mark a project clean when no project is open."
            )
        self._transition_to(ProjectState.CLEAN)

    def close(self):
        if not self.is_open:
            return
        self._transition_to(ProjectState.CLOSED)
        self._path = None
