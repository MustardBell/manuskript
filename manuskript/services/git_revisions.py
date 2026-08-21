import io
import logging
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass

from manuskript.domain.project_paths import normalize_project_path


#: Every Git command this project runs passes through one place, so this is
#: where a search that is stuck can be seen to be stuck, and in which command.
LOGGER = logging.getLogger(__name__)


class GitRevisionError(RuntimeError):
    """A Git revision operation could not be completed safely."""


class GitNotAvailableError(GitRevisionError):
    """Git is missing or the project is not inside a worktree."""


@dataclass(frozen=True)
class GitAvailability:
    """Why Git history is or is not usable for a project.

    The two reasons need telling apart in the interface: a missing Git is
    something the writer must fix outside Manuskript, while a project that
    simply is not in a repository yet can be fixed here.
    """

    git_installed: bool
    repository_root: object = None

    @property
    def usable(self):
        return self.git_installed and self.repository_root is not None

    @property
    def needs_repository(self):
        return self.git_installed and self.repository_root is None


def inspect_git_availability(project_file, runner=None):
    """Report Git usability without raising, for settings and status UI."""
    runner = runner or GitCommandRunner()
    if not runner.available:
        return GitAvailability(git_installed=False)
    if not project_file:
        return GitAvailability(git_installed=True)
    try:
        backend = GitRevisionBackend(project_file, runner=runner)
    except GitNotAvailableError:
        return GitAvailability(git_installed=True)
    except GitRevisionError:
        return GitAvailability(git_installed=True)
    return GitAvailability(
        git_installed=True,
        repository_root=backend.repository.root,
    )


@dataclass(frozen=True)
class GitCommandResult:
    arguments: tuple
    stdout: bytes
    stderr: bytes
    return_code: int


#: Variables that redirect Git at a repository other than the one we asked
#: about. ``GIT_DIR`` beats ``git -C`` outright, so a reader who exported it
#: in the shell that launched Manuskript would have every command answered
#: from somewhere else entirely -- silently, and with plausible results.
_REDIRECTING_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_CEILING_DIRECTORIES",
    "GIT_NAMESPACE",
)

#: How long any one Git command may take before it is treated as wedged.
#: Not a ration on how much history may be searched: the search reads as
#: many commits as it likes, and this bounds one external process. Without
#: it a single command that never returns is indistinguishable from a search
#: still working, because stderr is a pipe nobody is reading.
COMMAND_SECONDS = 120


class GitTimedOut(GitRevisionError):
    """One Git command took long enough to be treated as wedged."""


class GitCommandRunner:
    """Execute Git without a shell and preserve byte-exact object output."""

    def __init__(self, executable=None, run=None, timeout=COMMAND_SECONDS):
        self.executable = executable or shutil.which("git")
        self._run = run or subprocess.run
        self._timeout = timeout

    @property
    def available(self):
        return self.executable is not None

    def environment(self, overrides=None):
        """The environment Git is given: this one, minus the redirections.

        Sanitized centrally rather than at each call site, because the
        variables that do the damage are the ones nobody remembers to think
        about, and a caller that builds its own environment inherits this
        base rather than starting from ``os.environ``.
        """

        base = {
            name: value
            for name, value in os.environ.items()
            if name not in _REDIRECTING_VARIABLES
        }
        # Reading history must not become network access. A partly-cloned
        # repository will otherwise fetch a missing object from its promisor
        # remote in the middle of a search, which turns "where did this
        # paragraph come from" into a request that can wait on a network, a
        # credential helper, or nothing at all.
        base["GIT_NO_LAZY_FETCH"] = "1"
        # And nothing here may ever stop to ask a question. There is no
        # terminal to answer it on.
        base["GIT_TERMINAL_PROMPT"] = "0"
        base.update(overrides or {})
        return base

    def execute(self, arguments, *, stdin=None, environment=None):
        if not self.available:
            raise GitNotAvailableError(
                "Git is not installed or cannot be found."
            )

        command = (self.executable, *tuple(arguments))
        options = {
            "input": stdin,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "check": False,
            "env": self.environment(environment),
            "timeout": self._timeout,
        }
        started = time.monotonic()
        try:
            completed = self._run(list(command), **options)
        except subprocess.TimeoutExpired:
            LOGGER.error(
                "git %s did not return within %ss",
                " ".join(str(part) for part in arguments), self._timeout,
            )
            raise GitTimedOut(
                "Git did not answer within {} seconds: {}".format(
                    self._timeout,
                    " ".join(str(part) for part in arguments[:3]),
                )
            )
        elapsed = time.monotonic() - started
        # The whole command, not the first few words of it. Truncating kept
        # the log tidy and threw away the revision and the path -- which are
        # exactly what tells the source a stalled search was sitting in from
        # the three hundred before it.
        spoken = " ".join(str(part) for part in arguments)
        if elapsed > 1:
            LOGGER.info("git %s took %.1fs", spoken, elapsed)
        else:
            LOGGER.debug(
                "git %s -> %d in %.3fs", spoken, completed.returncode, elapsed
            )
        return GitCommandResult(
            arguments=command,
            stdout=completed.stdout,
            stderr=completed.stderr,
            return_code=completed.returncode,
        )


@dataclass(frozen=True)
class GitRepository:
    root: str
    git_dir: str
    project_file: str
    project_paths: tuple


@dataclass(frozen=True)
class GitWorkingTreeStatus:
    head: str
    branch: str
    staged: int = 0
    modified: int = 0
    untracked: int = 0
    conflicts: int = 0

    @property
    def dirty(self):
        return any((
            self.staged,
            self.modified,
            self.untracked,
            self.conflicts,
        ))


@dataclass(frozen=True)
class GitRevision:
    commit_id: str
    timestamp: int
    author_name: str
    author_email: str
    subject: str
    tags: tuple = ()
    #: Parent commit ids in Git's order, so a caller can tell a merge from a
    #: straight line and a first parent from the branch that joined.
    parents: tuple = ()
    #: False where Git is presenting a commit as a root that is not one. A
    #: shallow clone grafts its boundary commits to look parentless, so a
    #: caller reasoning about ancestry would otherwise call "as far back as
    #: this clone was given" the same thing as "as far back as there is".
    parents_complete: bool = True

    @property
    def short_id(self):
        return self.commit_id[:10]

    @property
    def tagged(self):
        return bool(self.tags)


@dataclass(frozen=True)
class GitProjectSnapshot:
    """A validated commit identity and its in-memory project files."""

    commit_id: str
    files: dict
    zipped: bool


class GitRevisionBackend:
    """Read project-scoped history from an existing Git worktree."""

    def __init__(self, project_file, runner=None):
        self.project_file = os.path.abspath(project_file)
        self.zipped = zipfile.is_zipfile(self.project_file)
        self.runner = runner or GitCommandRunner()
        self.repository = self._discover_repository()

    def _execute(
        self,
        arguments,
        *,
        allow_failure=False,
        stdin=None,
        environment=None,
    ):
        result = self.runner.execute((
            "-C",
            self.repository.root,
            *tuple(arguments),
        ), stdin=stdin, environment=environment)
        if result.return_code and not allow_failure:
            detail = result.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
            raise GitRevisionError(
                detail or "Git command failed."
            )
        return result

    def _discover_repository(self):
        if not self.runner.available:
            raise GitNotAvailableError(
                "Git is not installed or cannot be found."
            )

        candidates = [os.path.dirname(self.project_file)]
        project_directory = self._project_directory()
        if (
            project_directory is not None
            and project_directory != candidates[0]
            and os.path.isdir(project_directory)
        ):
            candidates.append(project_directory)

        for candidate in candidates:
            result = self.runner.execute((
                "-C",
                candidate,
                "rev-parse",
                "--show-toplevel",
                "--absolute-git-dir",
            ))
            if result.return_code:
                continue

            lines = result.stdout.decode(
                "utf-8",
                errors="surrogateescape",
            ).splitlines()
            if len(lines) < 2:
                continue
            root = os.path.abspath(lines[0])
            git_dir = os.path.abspath(lines[1])
            project_paths = self._project_paths(root)
            if project_paths:
                return GitRepository(
                    root=root,
                    git_dir=git_dir,
                    project_file=self.project_file,
                    project_paths=project_paths,
                )

        raise GitNotAvailableError(
            "The project is not contained in a Git worktree."
        )

    def _project_paths(self, root):
        candidates = [self.project_file]
        project_directory = self._project_directory()
        if (
            project_directory is not None
            and os.path.isdir(project_directory)
        ):
            candidates.append(project_directory)

        paths = []
        for candidate in candidates:
            candidate = os.path.abspath(candidate)
            try:
                within_root = os.path.commonpath((
                    root,
                    candidate,
                )) == root
            except ValueError:
                within_root = False
            if not within_root:
                continue
            relative = os.path.relpath(candidate, root)
            paths.append(
                "."
                if relative == os.curdir
                else relative.replace(os.sep, "/")
            )
        return tuple(dict.fromkeys(paths))

    def _project_directory(self):
        if self.zipped:
            return None
        directory = os.path.dirname(self.project_file)
        folder = os.path.splitext(
            os.path.basename(self.project_file)
        )[0]
        return os.path.join(directory, folder)

    def status(self):
        head_result = self._execute(
            ("rev-parse", "--verify", "HEAD"),
            allow_failure=True,
        )
        head = (
            head_result.stdout.decode("ascii").strip()
            if not head_result.return_code
            else ""
        )
        branch_result = self._execute(
            ("symbolic-ref", "--short", "-q", "HEAD"),
            allow_failure=True,
        )
        branch = (
            branch_result.stdout.decode(
                "utf-8",
                errors="replace",
            ).strip()
            if not branch_result.return_code
            else ""
        )
        status_result = self._execute((
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
            "--",
            *self.repository.project_paths,
        ))
        staged = modified = untracked = conflicts = 0
        for entry in status_result.stdout.split(b"\0"):
            if not entry:
                continue
            prefix = entry[:2]
            if prefix == b"? ":
                untracked += 1
                continue
            if prefix == b"u ":
                conflicts += 1
                continue
            if prefix not in (b"1 ", b"2 "):
                continue
            fields = entry.split(b" ", 2)
            if len(fields) < 2:
                continue
            state = fields[1]
            if len(state) != 2:
                continue
            if state[0:1] != b".":
                staged += 1
            if state[1:2] != b".":
                modified += 1

        return GitWorkingTreeStatus(
            head=head,
            branch=branch,
            staged=staged,
            modified=modified,
            untracked=untracked,
            conflicts=conflicts,
        )

    def history(self, *, tagged_only=False, limit=250):
        tags = self._tags_by_commit()
        parents = self._parents_by_commit()
        boundaries = self.shallow_boundaries()
        arguments = [
            "log",
            # Default path history prunes a side branch whose merge was
            # TREESAME to one parent, which for provenance means prose can
            # live in a reachable commit the search never sees. Reproduced:
            # a passage written on a branch, resolved away at the merge,
            # is absent from the default log and present under this flag.
            "--full-history",
            "--date-order",
            "-z",
            "--format=%H%x00%ct%x00%an%x00%ae%x00%s%x00",
        ]
        if limit and not tagged_only:
            arguments.append("--max-count={}".format(int(limit)))
        arguments.extend((
            "--",
            *self.repository.project_paths,
        ))
        result = self._execute(arguments, allow_failure=True)
        if result.return_code:
            # An unborn repository has no history, but is otherwise valid.
            if not self.status().head:
                return []
            detail = result.stderr.decode(
                "utf-8",
                errors="replace",
            ).strip()
            raise GitRevisionError(
                detail or "Cannot read Git history."
            )

        revisions = []
        for record in result.stdout.split(b"\0\0"):
            fields = record.strip(b"\0\n").split(b"\0")
            if len(fields) != 5:
                continue
            commit_id = fields[0].decode("ascii")
            revision = GitRevision(
                commit_id=commit_id,
                timestamp=int(fields[1]),
                author_name=fields[2].decode(
                    "utf-8",
                    errors="replace",
                ),
                author_email=fields[3].decode(
                    "utf-8",
                    errors="replace",
                ),
                subject=fields[4].decode(
                    "utf-8",
                    errors="replace",
                ),
                tags=tags.get(commit_id, ()),
                parents=parents.get(commit_id, ()),
                parents_complete=commit_id not in boundaries,
            )
            if tagged_only and not revision.tagged:
                continue
            revisions.append(revision)
            if tagged_only and limit and len(revisions) >= limit:
                break
        return revisions

    def shallow_boundaries(self):
        """Commits Git presents as roots because this clone stops there.

        Git records them in the shallow file, which is the only place the
        difference between "nothing precedes this" and "you were not given
        what precedes this" is written down. Traversal deliberately hides
        it: a shallow boundary looks exactly like a root to every command
        that walks parents.
        """

        result = self._execute(
            ("rev-parse", "--git-path", "shallow"), allow_failure=True
        )
        if result.return_code:
            return frozenset()
        location = result.stdout.decode("utf-8", errors="replace").strip()
        if not location:
            return frozenset()
        if not os.path.isabs(location):
            location = os.path.join(self.repository.root, location)
        try:
            with open(location, "r", encoding="utf-8") as handle:
                return frozenset(
                    line.strip() for line in handle if line.strip()
                )
        except OSError:
            return frozenset()

    def _parents_by_commit(self):
        """Parent ids per commit, asked for separately and on purpose.

        The history format packs fields between NUL bytes and separates
        records by two of them, so any empty field looks exactly like the end
        of a record. A root commit has no parents, so adding them to that
        format made root commits disappear. Tags are already fetched
        separately for their own reasons; parents join them.
        """

        # --parents is the whole point rather than decoration. History here
        # is limited to the project's paths, so the surviving commits are a
        # subsequence of the graph and their true parents are mostly not
        # among them. Git rewrites the edges to the nearest surviving
        # ancestor when asked, which makes the filtered history connected --
        # without it every commit looks like a first appearance, because
        # none of them can see its predecessor.
        result = self._execute((
            "log", "--full-history", "--parents", "--format=%H %P",
            "--", *self.repository.project_paths,
        ), allow_failure=True)
        if result.return_code:
            return {}
        found = {}
        for line in result.stdout.decode("ascii", errors="replace").split("\n"):
            identifiers = line.split()
            if identifiers:
                found[identifiers[0]] = tuple(identifiers[1:])
        return found

    def _tags_by_commit(self):
        result = self._execute((
            "for-each-ref",
            "--format=%(refname:short)%00%(objecttype)%00"
            "%(objectname)%00%(*objectname)%00",
            "refs/tags",
        ))
        tags = {}
        for line in result.stdout.splitlines():
            fields = line.split(b"\0")
            if len(fields) < 4:
                continue
            name, object_type, object_id, peeled_id = fields[:4]
            commit_id = (
                peeled_id
                if object_type == b"tag" and peeled_id
                else object_id
            ).decode("ascii")
            decoded_name = name.decode(
                "utf-8",
                errors="replace",
            )
            tags.setdefault(commit_id, []).append(decoded_name)
        return {
            commit_id: tuple(sorted(names))
            for commit_id, names in tags.items()
        }

    def revision_details(self, commit_id, *, maximum_bytes=2_000_000):
        commit_id = self.resolve_commit(commit_id)
        result = self._execute((
            "show",
            "--no-ext-diff",
            "--no-color",
            "--format=fuller",
            "--stat",
            "--patch",
            commit_id,
            "--",
            *self.repository.project_paths,
        ))
        output = result.stdout
        truncated = len(output) > maximum_bytes
        if truncated:
            output = output[:maximum_bytes]
        text = output.decode("utf-8", errors="replace")
        if truncated:
            text += "\n\n[Diff truncated by Manuskript]"
        return text

    def resolve_commit(self, revision):
        result = self._execute((
            "rev-parse",
            "--verify",
            "{}^{{commit}}".format(revision),
        ))
        return result.stdout.decode("ascii").strip()

    def commit(self, message):
        """Commit only project files without hooks or worktree mutation."""
        message = str(message).strip()
        if not message:
            raise GitRevisionError(
                "A commit message is required."
            )
        if self.status().conflicts:
            raise GitRevisionError(
                "Resolve project merge conflicts before committing."
            )

        head = self.status().head
        temporary_index = self._temporary_index_path()
        # Built on the sanitized base rather than on os.environ, so the one
        # place that legitimately sets a redirecting variable does not also
        # let through the seven it does not want.
        environment = {"GIT_INDEX_FILE": temporary_index}
        try:
            if head:
                self._execute(
                    ("read-tree", head),
                    environment=environment,
                )
            else:
                self._execute(
                    ("read-tree", "--empty"),
                    environment=environment,
                )
            self._execute((
                "add",
                "-A",
                "-f",
                "--",
                *self.repository.project_paths,
            ), environment=environment)

            changed = self._execute((
                "diff",
                "--cached",
                "--quiet",
                "--",
                *self.repository.project_paths,
            ), allow_failure=True, environment=environment)
            if changed.return_code == 0:
                return None
            if changed.return_code != 1:
                detail = changed.stderr.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                raise GitRevisionError(
                    detail or "Cannot compare project changes."
                )

            tree = self._execute(
                ("write-tree",),
                environment=environment,
            ).stdout.decode("ascii").strip()
            arguments = ["commit-tree", tree]
            if head:
                arguments.extend(("-p", head))
            commit_id = self._execute(
                arguments,
                stdin=(message + "\n").encode("utf-8"),
            ).stdout.decode("ascii").strip()

            update_arguments = [
                "update-ref",
                "-m",
                "Manuskript revision commit",
                "HEAD",
                commit_id,
            ]
            if head:
                update_arguments.append(head)
            else:
                update_arguments.append("0" * 40)
            self._execute(update_arguments)

            # Bring only this project's real index entries in line with
            # the new HEAD. Unrelated staged changes stay untouched.
            self._execute((
                "reset",
                "-q",
                commit_id,
                "--",
                *self.repository.project_paths,
            ))
            return commit_id
        finally:
            for path in (
                temporary_index,
                temporary_index + ".lock",
            ):
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass

    def create_tag(self, revision, name):
        """Create an immutable lightweight milestone without running hooks."""
        commit_id = self.resolve_commit(revision)
        name = str(name).strip()
        if not name:
            raise GitRevisionError("A tag name is required.")
        reference = "refs/tags/{}".format(name)
        validation = self._execute(
            ("check-ref-format", reference),
            allow_failure=True,
        )
        if validation.return_code:
            raise GitRevisionError(
                "The tag name is not valid."
            )
        self._execute((
            "update-ref",
            "-m",
            "Manuskript revision milestone",
            reference,
            commit_id,
            "0" * 40,
        ))
        return name

    def _temporary_index_path(self):
        directory = os.path.join(
            self.repository.git_dir,
            "manuskript",
        )
        os.makedirs(directory, exist_ok=True)
        descriptor, path = tempfile.mkstemp(
            prefix="revision-index-",
            dir=directory,
        )
        os.close(descriptor)
        # Git requires a missing path or a valid index, not an empty file.
        os.remove(path)
        return path

    def snapshot(self, revision):
        """Read a complete project snapshot without touching the worktree."""
        commit_id = self.resolve_commit(revision)
        entries = self.tree_entries(commit_id)
        blobs = self.read_blobs(
            tuple(entry[1] for entry in entries)
        )
        repository_files = {
            path: blobs[object_id]
            for path, object_id in entries
        }

        if self.zipped:
            files = self._files_from_zip_snapshot(repository_files)
            zipped = True
        else:
            files = self._files_from_folder_snapshot(repository_files)
            zipped = False

        if "settings.txt" not in files:
            raise GitRevisionError(
                "The selected commit does not contain a complete "
                "Manuskript project (settings.txt is missing)."
            )
        return GitProjectSnapshot(
            commit_id=commit_id,
            files=files,
            zipped=zipped,
        )

    def tree_entries(self, commit_id):
        """The project's files at a commit, as ``(path, blob id)`` pairs.

        Public because the Git history capability is built on it: a
        published surface should not rest on a name that reads as private.
        """

        result = self._execute((
            "ls-tree",
            "-r",
            "-z",
            commit_id,
            "--",
            *self.repository.project_paths,
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
            mode, object_type, object_id = fields
            if object_type != b"blob" or mode == b"120000":
                raise GitRevisionError(
                    "The selected project contains unsupported Git "
                    "objects (links or submodules)."
                )
            path = raw_path.decode(
                "utf-8",
                errors="surrogateescape",
            )
            entries.append((path, object_id.decode("ascii")))
        return entries

    def read_blobs(self, object_ids):
        """The bytes of project blobs, read in one batch, keyed by id."""

        object_ids = tuple(dict.fromkeys(object_ids))
        if not object_ids:
            return {}
        request = (
            "\n".join(object_ids) + "\n"
        ).encode("ascii")
        result = self._execute(
            ("cat-file", "--batch"),
            stdin=request,
        )
        stream = io.BytesIO(result.stdout)
        blobs = {}
        for requested_id in object_ids:
            header = stream.readline().rstrip(b"\n")
            fields = header.split(b" ")
            if len(fields) != 3 or fields[1] != b"blob":
                raise GitRevisionError(
                    "Git did not return the requested project blob."
                )
            object_id = fields[0].decode("ascii")
            size = int(fields[2])
            content = stream.read(size)
            if len(content) != size or stream.read(1) != b"\n":
                raise GitRevisionError(
                    "Git returned a truncated project blob."
                )
            blobs[requested_id] = content
            blobs[object_id] = content
        return blobs

    def _files_from_zip_snapshot(self, repository_files):
        relative_project_file = self._relative_to_repository(
            self.project_file
        )
        archive_content = repository_files.get(relative_project_file)
        if archive_content is None:
            raise GitRevisionError(
                "The selected commit does not contain the project file."
            )

        files = {}
        try:
            with zipfile.ZipFile(
                io.BytesIO(archive_content)
            ) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    try:
                        path = normalize_project_path(member.filename)
                    except ValueError:
                        raise GitRevisionError(
                            "The selected project archive contains "
                            "an unsafe path."
                        )
                    content = archive.read(member)
                    files[path] = self._decode_project_file(
                        path,
                        content,
                    )
        except (OSError, zipfile.BadZipFile) as error:
            raise GitRevisionError(
                "The selected commit contains an invalid project "
                "archive: {}".format(error)
            ) from error
        return files

    def _files_from_folder_snapshot(self, repository_files):
        project_directory = self._project_directory()
        relative_directory = self._relative_to_repository(
            project_directory
        )
        prefix = (
            ""
            if relative_directory == "."
            else relative_directory.rstrip("/") + "/"
        )
        files = {}
        for path, content in repository_files.items():
            if prefix and not path.startswith(prefix):
                continue
            relative = path[len(prefix):] if prefix else path
            if not relative:
                continue
            try:
                normalized = normalize_project_path(relative)
            except ValueError:
                raise GitRevisionError(
                    "The selected project contains an unsafe path."
                )
            files[normalized] = self._decode_project_file(
                normalized,
                content,
            )
        return files

    def _relative_to_repository(self, path):
        relative = os.path.relpath(
            os.path.abspath(path),
            self.repository.root,
        )
        return (
            "."
            if relative == os.curdir
            else relative.replace(os.sep, "/")
        )

    @staticmethod
    def _decode_project_file(path, content):
        if os.path.splitext(path)[1].lower() in {
            ".xml",
            ".opml",
        }:
            return content
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise GitRevisionError(
                "Project file {} is not valid UTF-8.".format(path)
            ) from error
