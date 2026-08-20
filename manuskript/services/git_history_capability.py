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

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional

from manuskript.plugins.leases import CAPABILITY_REVOKED
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
#: What was listed is not what is there any more.
GIT_SOURCE_CHANGED = "git.source_changed"
#: The file holds an unresolved merge, so its text is not anyone's prose.
GIT_UNMERGED = "git.unmerged"
#: The catalogue name this capability is granted under.
CAPABILITY_GIT_HISTORY_NAME = "git.history"


class GitSourceChanged(GitRevisionError):
    """The thing being read stopped being the thing that was listed."""


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
    #: Set when the grant itself was withdrawn, which is not a fact about
    #: this machine's Git and must not be reported as one.
    revoked: str = ""

    @property
    def usable(self):
        return self.installed and self.in_repository and self.enabled

    def __bool__(self):
        return self.usable

    @property
    def reason(self):
        if self.revoked:
            return self.revoked
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
class BlameOrigin:
    """Where Git says a run of lines was last written.

    Three states rather than a hash, because two of them are not commits and
    were being reported as if they were. Lines a writer has edited and not
    committed carry Git's all-zero identity, which is forty zeroes in a SHA-1
    repository and passed for a hash. And a commit Git stopped at is not
    necessarily where the words began: in a shallow clone it is merely as far
    back as the clone was allowed to look.

    A root commit is also reported by Git as a boundary, which is why
    ``truncated`` exists separately. At a true root "as far as Git looked" and
    "as far back as there is" are the same statement, and telling a reader
    their answer might be older when nothing is older teaches them to
    distrust the one certain answer.
    """

    commit_id: str = ""
    #: Not committed yet: a working-tree edit, or an unresolved conflict.
    uncommitted: bool = False
    #: Git would not look further back through this commit.
    boundary: bool = False
    #: And the history really is incomplete here, so the words may be older.
    truncated: bool = False


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


def _staged_entries(backend):
    """Project files in the index, at stage zero only.

    A conflicted path is reported at stages 1, 2 and 3 -- base, ours,
    theirs. Treating those as ordinary entries lets whichever survives a
    dictionary become "the staged file", chosen by parse order rather than
    by anything meaningful. Stage zero is the index; the rest is an
    unresolved argument, and prose is not read out of one.

    Symlinks are refused for the same reason tree entries refuse them: the
    target's text is not this project's prose, and following one leaves the
    scope the caller was granted.
    """

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
        mode, object_id, stage = fields
        if stage != b"0" or mode == b"120000":
            continue
        entries.append(GitFile(
            path=raw_path.decode("utf-8", errors="replace"),
            content_id=object_id.decode("ascii"),
        ))
    return tuple(entries)


def _working_entries(backend):
    """Project files on disk, tracked or not, that are really files.

    ``--cached`` reports the index, which remembers what disk no longer
    holds. And ``isfile`` follows symlinks, so a link inside the project
    pointing anywhere at all would be read as manuscript prose -- the same
    escape from project scope that refusing blob ids was meant to prevent.
    Both are settled here rather than trusted to the caller.
    """

    result = backend._execute((
        "ls-files", "--cached", "--others", "--exclude-standard",
        "-z", "--", *backend.repository.project_paths,
    ))
    root = os.path.realpath(backend.repository.root)
    found = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        path = record.decode("utf-8", errors="replace")
        location = os.path.join(root, path)
        if os.path.islink(location) or not os.path.isfile(location):
            continue
        resolved = os.path.realpath(location)
        if os.path.commonpath((root, resolved)) != root:
            continue
        found.append(GitFile(path=path, content_id=""))
    return tuple(found)


def _is_object_id(field):
    """Hexadecimal and nothing else, at whatever width this repository uses.

    Deliberately not a length test. SHA-1 identifiers are forty characters
    and SHA-256 identifiers are sixty-four, and code that checks for forty is
    describing one repository format while claiming to parse Git.
    """

    return bool(field) and all(
        character in "0123456789abcdef" for character in field
    )


def _uncommitted_id(identifier):
    """Git's identity for lines that are not in any commit: all zeroes."""

    return bool(identifier) and set(identifier) == {"0"}


def _parse_incremental_blame(payload):
    """Origins from ``git blame --incremental``, in the order Git reports.

    Parsed as the documented grammar -- a header of an object id and three
    line numbers, then tagged records until ``filename`` closes the entry,
    with unknown tags ignored so a future Git can add them.

    An earlier version parsed ``--porcelain`` by the *shape* of a line: four
    whitespace-separated fields whose first was forty characters long. That
    is a description of SHA-1 output rather than a rule, so in a SHA-256
    repository it matched nothing and the search reported success with no
    results. It could also match a line of prose that happened to contain a
    forty-character hexadecimal word. ``--incremental`` omits file contents
    altogether, which removes that second class of mistake by construction.

    The order is Git's resolution order: neither line order nor chronology,
    and callers must not present it as either.
    """

    seen = []
    boundaries = set()
    current = None
    for line in payload.decode("utf-8", errors="replace").splitlines():
        if current is None:
            fields = line.split(" ")
            if (
                len(fields) >= 4
                and _is_object_id(fields[0])
                and all(field.isdigit() for field in fields[1:4])
            ):
                current = fields[0]
                if current not in seen:
                    seen.append(current)
            continue
        if line == "boundary":
            boundaries.add(current)
        elif line.startswith("filename "):
            # The value is a quoted pathname, but it is only ever a
            # terminator here, so it is never unquoted and never trusted.
            current = None
    return tuple(
        BlameOrigin(
            commit_id="" if _uncommitted_id(identifier) else identifier,
            uncommitted=_uncommitted_id(identifier),
            boundary=identifier in boundaries,
        )
        for identifier in seen
    )


def _is_shallow(backend):
    """Whether this clone's history has a floor Git cannot see past."""

    result = backend._execute(("rev-parse", "--is-shallow-repository"))
    return result.stdout.decode("ascii", errors="replace").strip() == "true"


def _is_unmerged(backend, path):
    """Whether the path is in the middle of an unresolved merge."""

    result = backend._execute((
        "ls-files", "--unmerged", "-z", "--", path,
    ))
    return bool(result.stdout.strip(b"\0"))


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

    def read(self, path, expected_content_id=""):
        return self.capability.read_staged_file(path, expected_content_id)


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
            backend_factory=None, lease=None, grants=None,
            project_generation=None):
        self._project_file = project_file
        self._runner = runner
        self._enabled = bool(enabled)
        self._backend_factory = backend_factory or GitRevisionBackend
        #: The grant this object acts under, and the register that can take
        #: it away. Holding the object is not holding the authority: every
        #: call asks whether the lease is still live, and the host may
        #: withdraw it at any moment without this object knowing in advance.
        self._lease = lease
        self._grants = grants
        self._project_generation = project_generation

    # -- availability ----------------------------------------------------

    def availability(self):
        """Never fails, because a caller must be able to ask safely.

        A withdrawn grant is reported here as unusable rather than as a Git
        problem: the reader should be told the plugin may no longer ask,
        not that their Git is broken.
        """

        refusal = self._refusal()
        if refusal:
            return GitAvailabilitySnapshot(
                installed=False, in_repository=False, enabled=False,
                revoked=refusal,
            )
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

    def history(self, *, limit=None, tagged_only=False):
        """Commits touching this project, newest first.

        ``limit=None`` means all of them, and is the default because the
        callers that matter are asking about provenance. A limit here is a
        silent false negative: prose older than the cut is reported as
        absent rather than as unsearched, and no amount of care further
        down can recover a commit that was never offered.
        """

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
                    tagged_only=tagged_only, limit=limit or 0
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

        return self._answer(_staged_entries)

    def read_staged_file(self, path, expected_content_id=""):
        """One staged file's text, by the path the index lists it under.

        The index is not a snapshot. Listing it and then reading from it are
        two moments, and a writer staging work between them changes what the
        second one finds. A caller that remembers what it was offered can
        say so, and a mismatch is reported rather than served: the caller
        had been about to file the new bytes under the old identity, which
        would poison a cache keyed by that identity for the rest of the
        search.
        """

        wanted = str(path)

        def read(backend):
            staged = {
                entry.path: entry.content_id
                for entry in _staged_entries(backend)
            }
            if wanted not in staged:
                raise GitRevisionError(
                    "{!r} is not a staged project file.".format(wanted)
                )
            found = staged[wanted]
            if expected_content_id and found != expected_content_id:
                raise GitSourceChanged(
                    "{!r} was staged again while it was being read."
                    .format(wanted)
                )
            blobs = backend.read_blobs((found,))
            return blobs[found].decode("utf-8", errors="replace")

        return self._answer(read, source_changed=True)

    def working_files(self):
        """Project files on disk, tracked or not.

        Untracked prose has no content id, because Git has never seen it.
        The field is empty rather than invented.
        """

        return self._answer(_working_entries)

    def read_working_file(self, path):
        """One file's text from disk, scoped to what working_files lists."""

        wanted = str(path)

        def read(backend):
            listed = {entry.path for entry in _working_entries(backend)}
            if wanted not in listed:
                raise GitRevisionError(
                    "{!r} is not a project file in the working tree."
                    .format(wanted)
                )
            location = os.path.join(backend.repository.root, wanted)
            with open(location, "rb") as handle:
                return handle.read().decode("utf-8", errors="replace")

        return self._answer(read)

    def blame(self, path, ranges):
        """Which commits last wrote these lines, as evidence rather than proof.

        Blame is the fastest way to find where prose on disk came from, and
        it answers a narrower question than a reader asks. Git attributes
        each *line* to the revision that last modified it, so a passage whose
        surrounding sentence was edited yesterday is attributed to yesterday
        even though the words are years old. These are origin hints. What is
        earliest is settled by reading history, not here.

        Whitespace is ignored and moved text is followed within a file and
        between files, because prose gets reflowed and scenes get shuffled
        between chapters, and neither means the words are new.

        ``ranges`` is every line range worth asking about, so a passage a
        writer used twice is one call rather than one answer.
        """

        wanted = str(path)
        asked = tuple(
            (max(1, int(first)), max(1, int(last))) for first, last in ranges
        )

        def read(backend):
            if wanted not in {
                entry.path for entry in _working_entries(backend)
            }:
                raise GitRevisionError(
                    "{!r} is not a project file in the working tree."
                    .format(wanted)
                )
            if _is_unmerged(backend, wanted):
                # A conflicted file is not a manuscript. Its text is two
                # drafts and three markers, and because normalization throws
                # punctuation away, prose either side of a "=======" reads as
                # one continuous passage that no commit ever contained.
                raise GitError(
                    GIT_UNMERGED,
                    "{!r} has an unresolved merge, so where its text came "
                    "from cannot be answered until it is resolved."
                    .format(wanted),
                )
            if not asked:
                return ()
            arguments = ["blame", "--incremental", "-w", "-M", "-C"]
            for first, last in asked:
                arguments += ["-L", "{},{}".format(first, last)]
            arguments += ["--", wanted]
            result = backend._execute(tuple(arguments))
            origins = _parse_incremental_blame(result.stdout)
            if not any(origin.boundary for origin in origins):
                return origins
            # Only a shallow clone makes a boundary mean "there is more you
            # cannot see". Grafts and replacements are taken at face value:
            # this promises effective Git history, which is the history the
            # reader's own commands would show them.
            shallow = _is_shallow(backend)
            return tuple(
                replace(origin, truncated=origin.boundary and shallow)
                for origin in origins
            )

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

    def _refusal(self):
        """Whether this handle may still act, asked of the grant register.

        Deliberately not asked of the current manifest or the currently open
        project: authority that follows the world around is how a panel
        outliving its project came to hold authority over the next one.
        """

        if self._grants is None:
            return ""
        return self._grants.refusal(
            self._lease,
            capability=CAPABILITY_GIT_HISTORY_NAME,
            project_generation=self._project_generation,
        )

    def _answer(self, read, unknown_revision=False, source_changed=False):
        refusal = self._refusal()
        if refusal:
            return GitAnswer(error=GitError(CAPABILITY_REVOKED, refusal))
        try:
            snapshot = self.availability()
        except OSError as error:
            # Asking whether Git exists runs Git, and launching a process
            # can fail for reasons that are not Git's. "Never fails" has to
            # survive that too, or the promise holds only while nothing is
            # wrong.
            return GitAnswer(error=GitError(GIT_UNAVAILABLE, str(error)))
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
        except GitError as error:
            # A read that already knows which failure this is says so. The
            # alternative is flattening every refusal into "git failed",
            # which is exactly the ambiguity the code field exists to end.
            return GitAnswer(error=error)
        except GitNotAvailableError as error:
            return GitAnswer(error=GitError(GIT_UNAVAILABLE, str(error)))
        except GitSourceChanged as error:
            return GitAnswer(error=GitError(GIT_SOURCE_CHANGED, str(error)))
        except GitRevisionError as error:
            code = GIT_UNKNOWN_REVISION if unknown_revision else GIT_FAILED
            return GitAnswer(error=GitError(code, str(error)))
        except OSError as error:
            # The promise is to answer, not to raise, and the filesystem
            # does not know that. A file the index lists but disk does not
            # hold reached a caller as FileNotFoundError and ended a search
            # that should have skipped it.
            return GitAnswer(error=GitError(GIT_FAILED, str(error)))
