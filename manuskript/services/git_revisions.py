import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass


class GitRevisionError(RuntimeError):
    """A Git revision operation could not be completed safely."""


class GitNotAvailableError(GitRevisionError):
    """Git is missing or the project is not inside a worktree."""


@dataclass(frozen=True)
class GitCommandResult:
    arguments: tuple
    stdout: bytes
    stderr: bytes
    return_code: int


class GitCommandRunner:
    """Execute Git without a shell and preserve byte-exact object output."""

    def __init__(self, executable=None, run=None):
        self.executable = executable or shutil.which("git")
        self._run = run or subprocess.run

    @property
    def available(self):
        return self.executable is not None

    def execute(self, arguments, *, stdin=None):
        if not self.available:
            raise GitNotAvailableError(
                "Git is not installed or cannot be found."
            )

        command = (self.executable, *tuple(arguments))
        completed = self._run(
            list(command),
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
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

    @property
    def short_id(self):
        return self.commit_id[:10]

    @property
    def tagged(self):
        return bool(self.tags)


class GitRevisionBackend:
    """Read project-scoped history from an existing Git worktree."""

    def __init__(self, project_file, runner=None):
        self.project_file = os.path.abspath(project_file)
        self.runner = runner or GitCommandRunner()
        self.repository = self._discover_repository()

    def _execute(self, arguments, *, allow_failure=False):
        result = self.runner.execute((
            "-C",
            self.repository.root,
            *tuple(arguments),
        ))
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
            project_directory != candidates[0]
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
        if os.path.isdir(project_directory):
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
        if zipfile.is_zipfile(self.project_file):
            return os.path.dirname(self.project_file)
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
        arguments = [
            "log",
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
            )
            if tagged_only and not revision.tagged:
                continue
            revisions.append(revision)
            if tagged_only and limit and len(revisions) >= limit:
                break
        return revisions

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
