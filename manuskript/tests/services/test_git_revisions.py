import os
import subprocess

import pytest

from manuskript.services.git_revisions import (
    GitNotAvailableError,
    GitRevisionBackend,
)


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def write_project(repository, scene_text="First"):
    project_file = repository / "book.msk"
    project_file.write_text("1", encoding="utf-8")
    project_directory = repository / "book"
    outline = project_directory / "outline"
    outline.mkdir(parents=True, exist_ok=True)
    (project_directory / "settings.txt").write_text(
        "{}",
        encoding="utf-8",
    )
    (outline / "scene.md").write_text(
        scene_text,
        encoding="utf-8",
    )
    return project_file


@pytest.fixture
def git_project(tmp_path):
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.name", "Revision Tester")
    run_git(
        tmp_path,
        "config",
        "user.email",
        "revisions@example.test",
    )
    project_file = write_project(tmp_path)
    run_git(tmp_path, "add", "book.msk", "book")
    run_git(tmp_path, "commit", "-q", "-m", "Initial manuscript")
    return tmp_path, project_file


def test_discovers_project_scope_and_reads_history(git_project):
    repository, project_file = git_project
    write_project(repository, "Second")
    run_git(repository, "add", "book")
    run_git(repository, "commit", "-q", "-m", "Rewrite scene")

    backend = GitRevisionBackend(str(project_file))
    revisions = backend.history()

    assert backend.repository.root == str(repository)
    assert backend.repository.project_paths == ("book.msk", "book")
    assert [revision.subject for revision in revisions] == [
        "Rewrite scene",
        "Initial manuscript",
    ]
    assert revisions[0].author_name == "Revision Tester"


def test_history_can_be_limited_to_tagged_commits(git_project):
    repository, project_file = git_project
    first_commit = run_git(
        repository,
        "rev-parse",
        "HEAD",
    ).stdout.decode().strip()
    run_git(repository, "tag", "draft-one", first_commit)
    write_project(repository, "Second")
    run_git(repository, "add", "book")
    run_git(repository, "commit", "-q", "-m", "Untagged rewrite")

    revisions = GitRevisionBackend(
        str(project_file)
    ).history(tagged_only=True)

    assert len(revisions) == 1
    assert revisions[0].commit_id == first_commit
    assert revisions[0].tags == ("draft-one",)


def test_status_is_scoped_to_project_files(git_project):
    repository, project_file = git_project
    (repository / "book" / "outline" / "scene.md").write_text(
        "Modified",
        encoding="utf-8",
    )
    (repository / "book" / "notes.md").write_text(
        "Untracked",
        encoding="utf-8",
    )
    (repository / "unrelated.txt").write_text(
        "Ignored by project status",
        encoding="utf-8",
    )

    status = GitRevisionBackend(str(project_file)).status()

    assert status.dirty
    assert status.modified == 1
    assert status.untracked == 1
    assert status.staged == 0


def test_revision_details_are_scoped_to_project(git_project):
    repository, project_file = git_project
    revision = run_git(
        repository,
        "rev-parse",
        "HEAD",
    ).stdout.decode().strip()

    details = GitRevisionBackend(
        str(project_file)
    ).revision_details(revision)

    assert "Initial manuscript" in details
    assert "book/outline/scene.md" in details


def test_snapshot_reads_project_from_commit_without_changing_worktree(
    git_project,
):
    repository, project_file = git_project
    revision = run_git(
        repository,
        "rev-parse",
        "HEAD",
    ).stdout.decode().strip()
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("Current uncommitted text", encoding="utf-8")

    snapshot = GitRevisionBackend(str(project_file)).snapshot(revision)

    assert snapshot.commit_id == revision
    assert not snapshot.zipped
    assert snapshot.files["outline/scene.md"] == "First"
    assert scene.read_text(encoding="utf-8") == (
        "Current uncommitted text"
    )


def test_snapshot_rejects_commit_without_complete_project(
    git_project,
):
    repository, project_file = git_project
    run_git(repository, "rm", "-q", "book/settings.txt")
    run_git(repository, "commit", "-q", "-m", "Remove settings")

    backend = GitRevisionBackend(str(project_file))

    with pytest.raises(
        Exception,
        match="settings.txt is missing",
    ):
        backend.snapshot("HEAD")


def test_manual_commit_records_only_project_and_preserves_other_staging(
    git_project,
):
    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("Committed by Manuskript", encoding="utf-8")
    unrelated = repository / "unrelated.txt"
    unrelated.write_text("Staged elsewhere", encoding="utf-8")
    run_git(repository, "add", "unrelated.txt")

    commit_id = GitRevisionBackend(str(project_file)).commit(
        "Manual milestone candidate"
    )

    committed_scene = run_git(
        repository,
        "show",
        "{}:book/outline/scene.md".format(commit_id),
    ).stdout.decode()
    committed_paths = run_git(
        repository,
        "show",
        "--format=",
        "--name-only",
        commit_id,
    ).stdout.decode().splitlines()
    staged_paths = run_git(
        repository,
        "diff",
        "--cached",
        "--name-only",
    ).stdout.decode().splitlines()
    assert committed_scene == "Committed by Manuskript"
    assert "book/outline/scene.md" in committed_paths
    assert "unrelated.txt" not in committed_paths
    assert staged_paths == ["unrelated.txt"]


def test_manual_commit_returns_none_when_project_is_unchanged(
    git_project,
):
    _repository, project_file = git_project

    assert GitRevisionBackend(str(project_file)).commit(
        "Nothing changed"
    ) is None


def test_create_tag_makes_commit_visible_as_milestone(git_project):
    _repository, project_file = git_project
    backend = GitRevisionBackend(str(project_file))
    commit_id = backend.resolve_commit("HEAD")

    backend.create_tag(commit_id, "draft/one")

    revisions = backend.history(tagged_only=True)
    assert revisions[0].commit_id == commit_id
    assert revisions[0].tags == ("draft/one",)


def test_project_outside_git_repository_is_unavailable(tmp_path):
    project_file = write_project(tmp_path)

    with pytest.raises(
        GitNotAvailableError,
        match="not contained",
    ):
        GitRevisionBackend(str(project_file))
