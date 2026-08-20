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
