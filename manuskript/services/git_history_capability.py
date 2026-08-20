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

import os

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
class GitFile:
    """One project file at one revision.

    ``content_id`` is Git's identity for the bytes -- the blob object id.
    A caller that has already read those bytes at another revision can skip
    reading them again, which is the whole optimization for a file that sits
    unchanged across two hundred commits. It is a hint, not an address: a
    caller cannot ask for a content id, only for a path it is allowed to see.
    """

    path: str
    content_id: str


@dataclass(frozen=True)
class GitCommit:
    """One commit, in the terms a reader picks one out by."""

    commit_id: str
    timestamp: int
    subject: str
    author_name: str = ""
    tags: tuple = ()
    parents: tuple = ()

    @property
    def short_id(self):
        return self.commit_id[:10]


class TextSource:
    """Somewhere a passage of prose might be found.

    Committed revisions, the index and the working tree answer the same two
    questions -- what files are here, and what does one of them say -- but
    they answer them by entirely different means: tree plumbing, the staged
    index, and ordinary files on disk. Forcing all three through a
    revision-shaped pipeline would distort each of them, so each is its own
    strategy behind one small interface, and a caller iterates sources
    without knowing which kind it holds.
    """

    #: What to call this source when reporting a match found in it.
    label = ""
    #: Whether this source is a commit a reader can copy the hash of.
    commit_id = None

    def files(self):
        raise NotImplementedError

    def read(self, path):
        raise NotImplementedError


class CommittedRevision(TextSource):
    """One commit's trees, read through Git."""

    def __init__(self, capability, commit_id, subject=""):
        self.capability = capability
        self.commit_id = commit_id
        self.label = subject or commit_id[:10]

    def files(self):
        return self.capability.files(self.commit_id)

    def read(self, path):
        return self.capability.read_file(self.commit_id, path)


class StagedIndex(TextSource):
    """What is staged but not committed.

    Addressed through the index rather than a tree, because there is no
    commit to name. Prose a writer has staged and not yet committed is a
    perfectly good answer to where a passage came from.
    """

    label = "staged"

    def __init__(self, capability):
        self.capability = capability

    def files(self):
        return self.capability.staged_files()

    def read(self, path):
        return self.capability.read_staged_file(path)


class WorkingTree(TextSource):
    """What is on disk right now, including files never added.

    No Git plumbing at all: these are ordinary files. A passage the writer
    typed this morning and has not added is still theirs, and a search that
    could not see it would look broken rather than thorough.
    """

    label = "working tree"

    def __init__(self, capability):
        self.capability = capability

    def files(self):
        return self.capability.working_files()

    def read(self, path):
        return self.capability.read_working_file(path)


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
                    parents=tuple(getattr(revision, "parents", ())),
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
        """What is staged, modified or untracked right now, in counts."""

        return self._answer(lambda backend: backend.status())

    def files(self, revision):
        """The project's files at a revision, with their content identities.

        Scoped to the project. A repository may hold anything beside a
        manuscript, and none of it is a plugin's business.
        """

        def read(backend):
            commit_id = backend.resolve_commit(revision)
            return tuple(
                GitFile(path=path, content_id=content_id)
                for path, content_id in backend.tree_entries(commit_id)
            )

        return self._answer(read, unknown_revision=True)

    def read_file(self, revision, path):
        """One project file's text at a revision.

        Deliberately addressed by path and not by content id. An object id
        names anything in the repository, including files outside the
        project, so accepting one would hand out a way around the scoping
        that listing carefully applies.
        """

        wanted = str(path)

        def read(backend):
            commit_id = backend.resolve_commit(revision)
            entries = dict(backend.tree_entries(commit_id))
            if wanted not in entries:
                raise GitRevisionError(
                    "{!r} is not a project file at {}.".format(
                        wanted, commit_id[:10]
                    )
                )
            blobs = backend.read_blobs((entries[wanted],))
            content = blobs[entries[wanted]]
            return content.decode("utf-8", errors="replace")

        return self._answer(read, unknown_revision=True)

    # -- plumbing --------------------------------------------------------

    # -- the index and the working tree, which are not revisions ---------

    def staged_files(self):
        """Project files in the index, with their staged content ids."""

        def read(backend):
            result = backend._execute((
                "ls-files", "--stage", "-z", "--",
                *backend.repository.project_paths,
            ))
            entries = []
            for record in result.stdout.split(b"\0"):
                if not record:
                    continue
                metadata, separator, raw_path = record.partition(b"\t")
                if not separator:
                    continue
                fields = metadata.split(b" ")
                if len(fields) != 3:
                    continue
                entries.append(GitFile(
                    path=raw_path.decode("utf-8", errors="replace"),
                    content_id=fields[1].decode("ascii"),
                ))
            return tuple(entries)

        return self._answer(read)

    def read_staged_file(self, path):
        """One staged file's text, by the path the index lists it under."""

        wanted = str(path)

        def read(backend):
            staged = {
                entry.path: entry.content_id
                for entry in self.staged_files().unwrap()
            }
            if wanted not in staged:
                raise GitRevisionError(
                    "{!r} is not a staged project file.".format(wanted)
                )
            blobs = backend.read_blobs((staged[wanted],))
            return blobs[staged[wanted]].decode("utf-8", errors="replace")

        return self._answer(read)

    def working_files(self):
        """Project files on disk, tracked or not.

        Untracked prose has no content id, because Git has never seen it.
        The field is empty rather than invented.
        """

        def read(backend):
            result = backend._execute((
                "ls-files", "--cached", "--others", "--exclude-standard",
                "-z", "--", *backend.repository.project_paths,
            ))
            return tuple(
                GitFile(path=record.decode("utf-8", errors="replace"),
                        content_id="")
                for record in result.stdout.split(b"\0")
                if record
            )

        return self._answer(read)

    def read_working_file(self, path):
        """One file's text from disk, scoped to what working_files lists."""

        wanted = str(path)

        def read(backend):
            listed = {entry.path for entry in self.working_files().unwrap()}
            if wanted not in listed:
                raise GitRevisionError(
                    "{!r} is not a project file in the working tree."
                    .format(wanted)
                )
            location = os.path.join(backend.repository.root, wanted)
            with open(location, "rb") as handle:
                return handle.read().decode("utf-8", errors="replace")

        return self._answer(read)

    def sources(self, revisions=()):
        """Every place a passage might be, newest first.

        The working tree and the index come first because prose found there
        is the most recent it could be, and a reader hunting for where
        something came from wants to know it is not yet committed.
        """

        found = [WorkingTree(self), StagedIndex(self)]
        for commit in revisions:
            found.append(CommittedRevision(
                self,
                getattr(commit, "commit_id", commit),
                getattr(commit, "subject", ""),
            ))
        return tuple(found)

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
