"""Asking about Git must be safe, and not asking must not be punished.

The capability answers with values, including when the answer is a failure.
Nothing it does raises, because an exception cannot cross a process boundary
and this surface is meant to survive being served over one.
"""

import pytest

from manuskript.services.git_history_capability import (
    GIT_UNAVAILABLE,
    GitAnswer,
    GitError,
    GitHistoryCapability,
)
from manuskript.services.git_revisions import (
    GitRevisionError,
    GitWorkingTreeStatus,
)


class FakeBackend:
    """Stands in for a worktree, including by failing like one."""

    def __init__(self, project_file, runner=None, failure=None):
        self.project_file = project_file
        self.failure = failure

    def history(self, *, tagged_only=False, limit=250):
        if self.failure:
            raise self.failure
        return ()

    def resolve_commit(self, revision):
        if self.failure:
            raise self.failure
        return "0123456789abcdef"

    def status(self):
        if self.failure:
            raise self.failure
        return GitWorkingTreeStatus(head="abc", branch="main", untracked=2)


def capability(monkeypatch, *, installed=True, in_repository=True,
               enabled=True, failure=None):
    import manuskript.services.git_history_capability as module

    class Report:
        git_installed = installed
        repository_root = "/repo" if in_repository else None

    monkeypatch.setattr(
        module, "inspect_git_availability",
        lambda project_file, runner=None: Report(),
    )
    return GitHistoryCapability(
        "/project/book.msk",
        enabled=enabled,
        backend_factory=lambda project_file, runner=None: FakeBackend(
            project_file, runner, failure
        ),
    )


def test_a_caller_can_ask_whether_git_is_usable():
    assert GitAnswer(value=1)
    assert not GitAnswer(error=GitError("x", "y"))


def test_availability_answers_without_git_installed(monkeypatch):
    git = capability(monkeypatch, installed=False)

    snapshot = git.availability()

    assert not git.is_available()
    assert not snapshot
    assert "not installed" in snapshot.reason


def test_a_project_outside_a_repository_is_told_apart_from_missing_git(
        monkeypatch):
    git = capability(monkeypatch, in_repository=False)

    snapshot = git.availability()

    assert snapshot.installed
    assert not snapshot.usable
    assert "not inside a Git repository" in snapshot.reason


def test_switched_off_is_a_third_reason(monkeypatch):
    """A plugin observes this and cannot change it."""

    git = capability(monkeypatch, enabled=False)

    assert not git.is_available()
    assert "switched off" in git.availability().reason


def test_calling_without_asking_first_returns_the_error_rather_than_raising(
        monkeypatch):
    git = capability(monkeypatch, installed=False)

    answer = git.history()

    assert not answer.ok
    assert answer.value is None
    assert answer.error.code == GIT_UNAVAILABLE
    assert answer.error.data["installed"] is False


def test_the_carried_error_is_a_real_exception_the_caller_may_raise(
        monkeypatch):
    git = capability(monkeypatch, installed=False)

    answer = git.history()

    assert isinstance(answer.error, Exception)
    with pytest.raises(GitError):
        answer.unwrap()


def test_an_error_survives_being_turned_into_a_record(monkeypatch):
    """What crosses a process boundary is the record, not the exception."""

    git = capability(monkeypatch, in_repository=False)

    record = git.history().error.as_record()

    assert record["code"] == GIT_UNAVAILABLE
    assert record["message"]
    assert record["data"]["in_repository"] is False


def test_a_failing_git_answers_instead_of_raising(monkeypatch):
    git = capability(
        monkeypatch, failure=GitRevisionError("object not found")
    )

    answer = git.resolve("deadbeef")

    assert not answer.ok
    assert "not found" in answer.error.message


def test_a_working_answer_carries_no_error(monkeypatch):
    git = capability(monkeypatch)

    answer = git.resolve("HEAD")

    assert answer.ok
    assert answer.unwrap() == "0123456789abcdef"
    assert answer.error is None


def test_the_working_tree_is_readable_for_uncommitted_text(monkeypatch):
    """Text a writer is hunting for may be staged, or not added at all."""

    git = capability(monkeypatch)

    status = git.working_tree().unwrap()

    assert status.untracked == 2


def test_the_capability_is_reachable_through_the_plugin_resolver():
    """A plugin asks for it by the catalogue name, like any other service."""

    from types import SimpleNamespace
    from manuskript.plugins.capabilities import CAPABILITY_GIT_HISTORY
    from manuskript.ui.plugins.story_capabilities import (
        build_story_capability,
    )

    runtime = SimpleNamespace(declares=lambda plugin_id, name: True)
    manager = SimpleNamespace(
        session=SimpleNamespace(is_open=True),
        currentProject="/project/book.msk",
        settings=SimpleNamespace(revisions={"backend": "git"}),
    )

    capability = build_story_capability(
        runtime, manager, "vendor.provenance", CAPABILITY_GIT_HISTORY
    )

    assert isinstance(capability, GitHistoryCapability)


def test_a_plugin_that_did_not_declare_it_is_refused_at_resolution():
    """Rule 3 governs Git failures, not manifest violations.

    Asking for a capability the manifest never declared is a scope error and
    still raises: the plugin is not entitled to the object at all, which is a
    different matter from Git being unavailable to a plugin that is.
    """

    from types import SimpleNamespace
    from manuskript.plugins.capabilities import CAPABILITY_GIT_HISTORY
    from manuskript.plugins.errors import PluginScopeError
    from manuskript.ui.plugins.story_capabilities import (
        build_story_capability,
    )

    runtime = SimpleNamespace(declares=lambda plugin_id, name: False)
    manager = SimpleNamespace(session=SimpleNamespace(is_open=True))

    with pytest.raises(PluginScopeError):
        build_story_capability(
            runtime, manager, "vendor.provenance", CAPABILITY_GIT_HISTORY
        )


def test_the_capability_is_published_in_the_catalogue():
    """A resolver without a catalogue entry is a capability nobody can ask for.

    The entry was missing while the resolver existed, and the resolver test
    hid it by supplying a runtime that declares everything.
    """

    from manuskript.plugins.capabilities import (
        CAPABILITY_GIT_HISTORY,
        capability_catalogue,
    )

    assert CAPABILITY_GIT_HISTORY in capability_catalogue()


class TreeBackend(FakeBackend):
    """A worktree with two project files, one of them unchanged."""

    ENTRIES = (
        ("book/chapter-1.md", "aaaa111"),
        ("book/chapter-2.md", "bbbb222"),
    )

    def resolve_commit(self, revision):
        if revision == "nope":
            raise GitRevisionError("unknown revision")
        return "0123456789abcdef"

    def tree_entries(self, commit_id):
        return list(self.ENTRIES)

    def read_blobs(self, object_ids):
        return {
            object_id: "She left quietly.".encode("utf-8")
            for object_id in object_ids
        }


def tree_capability(monkeypatch):
    import manuskript.services.git_history_capability as module

    class Report:
        git_installed = True
        repository_root = "/repo"

    monkeypatch.setattr(
        module, "inspect_git_availability",
        lambda project_file, runner=None: Report(),
    )
    return GitHistoryCapability(
        "/project/book.msk",
        backend_factory=lambda project_file, runner=None: TreeBackend(
            project_file, runner
        ),
    )


def test_listing_a_revision_carries_content_identities(monkeypatch):
    """The identity is what lets a caller skip a blob it has already read."""

    git = tree_capability(monkeypatch)

    files = git.files("HEAD").unwrap()

    assert [entry.path for entry in files] == [
        "book/chapter-1.md", "book/chapter-2.md",
    ]
    assert files[0].content_id == "aaaa111"


def test_a_project_file_reads_back_as_text(monkeypatch):
    git = tree_capability(monkeypatch)

    assert git.read_file("HEAD", "book/chapter-1.md").unwrap() == (
        "She left quietly."
    )


def test_a_path_outside_the_project_is_refused(monkeypatch):
    """Listing is scoped, so reading must be scoped by the same list.

    Addressing by content id instead would hand out a way around that: an
    object id names anything in the repository.
    """

    git = tree_capability(monkeypatch)

    answer = git.read_file("HEAD", "../../etc/passwd")

    assert not answer.ok
    assert "not a project file" in answer.error.message


def test_reading_at_an_unknown_revision_answers_rather_than_raises(
        monkeypatch):
    git = tree_capability(monkeypatch)

    answer = git.read_file("nope", "book/chapter-1.md")

    assert not answer.ok
    assert answer.error.code == "git.unknown_revision"


class SourcesBackend(TreeBackend):
    """Answers the index and the working tree as Git plumbing would."""

    def __init__(self, project_file, runner=None, root=None):
        super().__init__(project_file, runner)
        self.repository = type("Repo", (), {
            "root": root or "/repo",
            "project_paths": ("book",),
        })()

    def _execute(self, arguments, **kwargs):
        joined = " ".join(arguments)
        if "--stage" in joined:
            payload = b"100644 cccc333 0\tbook/staged.md\x00"
        else:
            payload = b"book/chapter-1.md\x00book/untracked.md\x00"
        return type("Result", (), {"stdout": payload})()


def sources_capability(monkeypatch, root=None):
    import manuskript.services.git_history_capability as module

    class Report:
        git_installed = True
        repository_root = "/repo"

    monkeypatch.setattr(
        module, "inspect_git_availability",
        lambda project_file, runner=None: Report(),
    )
    return GitHistoryCapability(
        "/project/book.msk",
        backend_factory=lambda project_file, runner=None: SourcesBackend(
            project_file, runner, root
        ),
    )


def test_staged_prose_is_its_own_source_not_a_revision(monkeypatch):
    """There is no commit to name, so it is not addressed like one."""

    git = sources_capability(monkeypatch)

    staged = git.staged_files().unwrap()

    assert [entry.path for entry in staged] == ["book/staged.md"]
    assert staged[0].content_id == "cccc333"


def test_untracked_prose_has_no_content_identity(monkeypatch, tmp_path):
    """Git has never seen it, so the field is empty rather than invented."""

    (tmp_path / "book").mkdir()
    for name in ("chapter-1.md", "untracked.md"):
        (tmp_path / "book" / name).write_text("prose", encoding="utf-8")
    git = sources_capability(monkeypatch, root=str(tmp_path))

    working = git.working_files().unwrap()

    assert "book/untracked.md" in [entry.path for entry in working]
    assert all(entry.content_id == "" for entry in working)


def test_a_working_file_outside_the_listing_is_refused(monkeypatch, tmp_path):
    git = sources_capability(monkeypatch, root=str(tmp_path))

    answer = git.read_working_file("../secrets.txt")

    assert not answer.ok
    assert "not a project file" in answer.error.message


def test_a_working_file_reads_from_disk(monkeypatch, tmp_path):
    (tmp_path / "book").mkdir()
    (tmp_path / "book" / "chapter-1.md").write_text(
        "Typed this morning.", encoding="utf-8"
    )
    git = sources_capability(monkeypatch, root=str(tmp_path))

    assert git.read_working_file("book/chapter-1.md").unwrap() == (
        "Typed this morning."
    )


def test_sources_put_uncommitted_prose_first(monkeypatch):
    """Prose found on disk is the most recent it could be, so it leads."""

    from manuskript.services.git_history_capability import (
        CommittedRevision, StagedIndex, WorkingTree,
    )

    git = sources_capability(monkeypatch)

    found = git.sources(revisions=("abc1234def",))

    assert isinstance(found[0], WorkingTree)
    assert isinstance(found[1], StagedIndex)
    assert isinstance(found[2], CommittedRevision)
    assert found[2].commit_id == "abc1234def"
    assert [source.label for source in found[:2]] == [
        "working tree", "staged",
    ]


def test_an_os_failure_is_answered_rather_than_raised(monkeypatch, tmp_path):
    """The promise is to answer. The filesystem does not know that.

    A file the index lists but the disk does not hold reached a caller as
    FileNotFoundError and ended a search that should have skipped it.
    """

    git = sources_capability(monkeypatch, root=str(tmp_path))
    (tmp_path / "book").mkdir()
    (tmp_path / "book" / "chapter-1.md").write_text("x", encoding="utf-8")

    listed = git.working_files().unwrap()
    (tmp_path / "book" / "chapter-1.md").unlink()
    answer = git.read_working_file(listed[0].path)

    assert not answer.ok
    assert isinstance(answer.error, GitError)


def test_the_working_tree_does_not_offer_files_the_disk_lacks(
        monkeypatch, tmp_path):
    """--cached remembers staged deletions and renames; disk is the truth."""

    git = sources_capability(monkeypatch, root=str(tmp_path))
    (tmp_path / "book").mkdir()
    (tmp_path / "book" / "chapter-1.md").write_text("here", encoding="utf-8")

    listed = [entry.path for entry in git.working_files().unwrap()]

    # The double lists chapter-1.md and untracked.md; only the first exists.
    assert "book/chapter-1.md" in listed
    assert "book/untracked.md" not in listed


class ConflictBackend(SourcesBackend):
    """An index mid-merge, and a symlink pointing out of the project."""

    def _execute(self, arguments, **kwargs):
        joined = " ".join(arguments)
        if "--stage" in joined:
            payload = (
                b"100644 aaa111 1\tbook/fight.md\x00"
                b"100644 bbb222 2\tbook/fight.md\x00"
                b"100644 ccc333 3\tbook/fight.md\x00"
                b"100644 ddd444 0\tbook/calm.md\x00"
                b"120000 eee555 0\tbook/link.md\x00"
            )
        else:
            payload = b"book/calm.md\x00book/escape.md\x00"
        return type("Result", (), {"stdout": payload})()


def conflict_capability(monkeypatch, root):
    import manuskript.services.git_history_capability as module

    class Report:
        git_installed = True
        repository_root = root

    monkeypatch.setattr(
        module, "inspect_git_availability",
        lambda project_file, runner=None: Report(),
    )
    return GitHistoryCapability(
        "/project/book.msk",
        backend_factory=lambda project_file, runner=None: ConflictBackend(
            project_file, runner, root
        ),
    )


def test_a_conflicted_path_is_not_offered_as_staged_prose(
        monkeypatch, tmp_path):
    """Stages one, two and three are an unresolved argument, not a file."""

    git = conflict_capability(monkeypatch, str(tmp_path))

    staged = {entry.path for entry in git.staged_files().unwrap()}

    assert "book/fight.md" not in staged
    assert "book/calm.md" in staged


def test_a_staged_symlink_is_not_read_as_prose(monkeypatch, tmp_path):
    git = conflict_capability(monkeypatch, str(tmp_path))

    staged = {entry.path for entry in git.staged_files().unwrap()}

    assert "book/link.md" not in staged


def test_a_working_symlink_cannot_reach_outside_the_project(
        monkeypatch, tmp_path):
    """isfile follows links, so the check has to refuse them itself.

    A link inside the project pointing anywhere at all would otherwise be
    read as manuscript prose -- the escape that refusing blob ids was meant
    to prevent, arriving by another door.
    """

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("not the manuscript", encoding="utf-8")
    root = tmp_path / "repo"
    (root / "book").mkdir(parents=True)
    (root / "book" / "calm.md").write_text("prose", encoding="utf-8")
    (root / "book" / "escape.md").symlink_to(outside)
    git = conflict_capability(monkeypatch, str(root))

    listed = {entry.path for entry in git.working_files().unwrap()}

    assert "book/calm.md" in listed
    assert "book/escape.md" not in listed
    assert not git.read_working_file("book/escape.md").ok


def test_a_staged_file_read_after_it_changed_is_refused(monkeypatch, tmp_path):
    """Listing and reading are two moments, and the index moves between them.

    Serving the new bytes under the identity the caller was given would let
    a search file blob B's text under blob A's name, and every later commit
    holding A would then be answered from B.
    """

    git = conflict_capability(monkeypatch, str(tmp_path))

    stale = git.read_staged_file("book/calm.md", expected_content_id="old")

    assert not stale.ok
    assert stale.error.code == "git.source_changed"
