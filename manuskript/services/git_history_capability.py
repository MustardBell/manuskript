"""Reading Git history, as a service that never raises at its boundary.

Three rules shape this, and they are the user's:

A caller asks whether Git is usable before relying on it, and
``is_available`` answers plainly. Nothing enforces the asking: a caller that
skips it is not punished, it simply receives an answer carrying an error
instead of a value.

Errors are returned, never thrown. Every method answers with a ``GitAnswer``
holding either a value or a ``GitError`` -- which is a real exception object
the caller may raise, report or ignore. This is not a stylistic choice: an
exception cannot cross a process boundary and a value can, and API 1 already
requires stable error records with a code, a message and bounded data for
anything that might one day be served over RPC.

Availability is not a plugin's to change. Whether Git is installed, whether
the project sits in a worktree, and whether the reader has enabled revisions
are facts about the machine, the project and the reader's settings. A caller
observes them.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from manuskript.services.git_revisions import (
    GitNotAvailableError,
    GitRevisionBackend,
    GitRevisionError,
    inspect_git_availability,
)


#: Git is not installed, or the project is not inside a worktree.
GIT_UNAVAILABLE = "git.unavailable"
#: Git is present but the operation itself failed.
GIT_FAILED = "git.failed"
#: The caller asked for something Git could not identify.
GIT_UNKNOWN_REVISION = "git.unknown_revision"


class GitError(RuntimeError):
    """A failure worth carrying around before deciding to raise it.

    Carries a stable ``code`` and bounded ``data`` beside the message, so the
    same failure survives being turned into a record and sent somewhere that
    cannot receive an exception.
    """

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.data = dict(data or {})

    def as_record(self):
        return {
            "code": self.code,
            "message": self.message,
            "data": dict(self.data),
        }


@dataclass(frozen=True)
class GitAnswer:
    """Either a value or an error. Never both, never neither raised."""

    value: Any = None
    error: Optional[GitError] = None

    @property
    def ok(self):
        return self.error is None

    def __bool__(self):
        return self.ok

    def unwrap(self):
        """The value, raising the carried error if there is one.

        The only place an error becomes an exception, and only because a
        caller asked for that.
        """

        if self.error is not None:
            raise self.error
        return self.value


@dataclass(frozen=True)
class GitAvailabilitySnapshot:
    """Why history is or is not readable, in terms a reader can act on."""

    installed: bool
    in_repository: bool
    enabled: bool = True
    repository_root: Optional[str] = None

    @property
    def usable(self):
        return self.installed and self.in_repository and self.enabled

    def __bool__(self):
        return self.usable

    @property
    def reason(self):
        if not self.installed:
            return "Git is not installed on this machine."
        if not self.in_repository:
            return "This project is not inside a Git repository."
        if not self.enabled:
            return "Git revisions are switched off for this project."
        return ""


@dataclass(frozen=True)
class GitCommit:
    """One commit, in the terms a reader picks one out by."""

    commit_id: str
    timestamp: int
    subject: str
    author_name: str = ""
    tags: tuple = ()

    @property
    def short_id(self):
        return self.commit_id[:10]


class GitHistoryCapability:
    """Read-only history for one project.

    Reading history and writing commits are different authorities and are
    deliberately not the same object: a caller granted the first cannot
    reach the second.
    """

    def __init__(
            self, project_file, runner=None, enabled=True,
            backend_factory=None):
        self._project_file = project_file
        self._runner = runner
        self._enabled = bool(enabled)
        self._backend_factory = backend_factory or GitRevisionBackend

    # -- availability ----------------------------------------------------

    def availability(self):
        """Never fails, because a caller must be able to ask safely."""

        report = inspect_git_availability(
            self._project_file, runner=self._runner
        )
        return GitAvailabilitySnapshot(
            installed=bool(report.git_installed),
            in_repository=report.repository_root is not None,
            enabled=self._enabled,
            repository_root=(
                str(report.repository_root)
                if report.repository_root is not None
                else None
            ),
        )

    def is_available(self):
        return self.availability().usable

    # -- reading ---------------------------------------------------------

    def history(self, *, limit=250, tagged_only=False):
        """Commits touching this project, newest first."""

        def read(backend):
            return tuple(
                GitCommit(
                    commit_id=revision.commit_id,
                    timestamp=revision.timestamp,
                    subject=revision.subject,
                    author_name=revision.author_name,
                    tags=tuple(revision.tags),
                )
                for revision in backend.history(
                    tagged_only=tagged_only, limit=limit
                )
            )

        return self._answer(read)

    def resolve(self, revision):
        """The commit id a revision expression names."""

        return self._answer(
            lambda backend: backend.resolve_commit(revision),
            unknown_revision=True,
        )

    def working_tree(self):
        """What is staged, modified or untracked right now."""

        return self._answer(lambda backend: backend.status())

    # -- plumbing --------------------------------------------------------

    def _answer(self, read, unknown_revision=False):
        snapshot = self.availability()
        if not snapshot.usable:
            return GitAnswer(error=GitError(
                GIT_UNAVAILABLE,
                snapshot.reason,
                {
                    "installed": snapshot.installed,
                    "in_repository": snapshot.in_repository,
                    "enabled": snapshot.enabled,
                },
            ))
        try:
            backend = self._backend_factory(
                self._project_file, runner=self._runner
            )
            return GitAnswer(value=read(backend))
        except GitNotAvailableError as error:
            return GitAnswer(error=GitError(GIT_UNAVAILABLE, str(error)))
        except GitRevisionError as error:
            code = GIT_UNKNOWN_REVISION if unknown_revision else GIT_FAILED
            return GitAnswer(error=GitError(code, str(error)))
