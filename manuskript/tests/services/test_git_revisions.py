import os
import subprocess
import zipfile

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


def test_zipped_project_scope_contains_only_archive(tmp_path):
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.name", "Revision Tester")
    run_git(
        tmp_path,
        "config",
        "user.email",
        "revisions@example.test",
    )
    project_file = tmp_path / "book.msk"
    with zipfile.ZipFile(project_file, "w") as archive:
        archive.writestr("settings.txt", "{}")
        archive.writestr("outline/scene.md", "First")
    (tmp_path / "unrelated.txt").write_text(
        "Not part of project",
        encoding="utf-8",
    )
    run_git(tmp_path, "add", "book.msk", "unrelated.txt")
    run_git(tmp_path, "commit", "-q", "-m", "Initial archive")
    revision = run_git(
        tmp_path,
        "rev-parse",
        "HEAD",
    ).stdout.decode().strip()

    backend = GitRevisionBackend(str(project_file))
    snapshot = backend.snapshot(revision)

    assert backend.repository.project_paths == ("book.msk",)
    assert snapshot.zipped
    assert snapshot.files["outline/scene.md"] == "First"


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


def test_history_carries_parents_including_for_a_root_commit(git_project):
    """A root commit has no parents, and must not vanish for saying so.

    Packing parents into the history format made exactly that happen: the
    fields are NUL-separated and records are separated by two NULs, so an
    empty trailing field ended the record early and the first commit in the
    repository disappeared from its own history.
    """

    repository, project_file = git_project
    backend = GitRevisionBackend(project_file)

    revisions = backend.history()

    assert revisions, "the root commit must still be reported"
    assert revisions[-1].parents == ()
    if len(revisions) > 1:
        assert revisions[0].parents == (revisions[1].commit_id,)


def test_parents_connect_the_history_that_was_actually_searched(git_project):
    """History is limited to the project, so its edges must be too.

    The log is filtered to project paths, which makes the surviving commits
    a subsequence of the graph. Their true parents are mostly not among
    them, so a caller asking "did this commit's parent already have the
    passage?" always heard no, and every match looked like a first
    appearance. Git rewrites the edges to the nearest surviving ancestor
    when asked; this checks that it was asked.
    """

    repository, project_file = git_project
    # A commit that does not touch the project at all, between two that do.
    (repository / "unrelated.txt").write_text("noise", encoding="utf-8")
    run_git(repository, "add", "unrelated.txt")
    run_git(repository, "commit", "-m", "unrelated work")
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("Later prose", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "later scene")

    revisions = GitRevisionBackend(project_file).history()
    identifiers = [revision.commit_id for revision in revisions]

    assert len(revisions) >= 2
    # Every commit but the oldest points at the next one in the searched
    # history, rather than at a commit the search never looked at.
    for newer, older in zip(revisions, revisions[1:]):
        assert older.commit_id in newer.parents, (
            "the filtered history is not connected"
        )
    assert revisions[-1].parents == ()
    assert "unrelated work" not in [
        revision.subject for revision in revisions
    ]
    assert len(set(identifiers)) == len(identifiers)


def test_history_keeps_a_branch_whose_merge_resolved_against_it(git_project):
    """Default path simplification loses provenance.

    Git may prune a side branch entirely when the merge is TREESAME to one
    parent. For provenance that means prose can live in a reachable commit
    the search never sees: written on a branch, resolved away at the merge,
    absent from the log and therefore reported as never having existed.
    """

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    run_git(repository, "checkout", "-b", "side")
    scene.write_text("secret passage", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "side prose")
    run_git(repository, "checkout", "-")
    scene.write_text("trunk prose", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "trunk prose")
    run_git(repository, "merge", "--no-commit", "-s", "ours", "side")
    run_git(repository, "commit", "-m", "merge keeping trunk")

    subjects = [
        revision.subject
        for revision in GitRevisionBackend(project_file).history()
    ]

    assert "side prose" in subjects, (
        "the branch the merge resolved against was pruned from history"
    )
    assert "merge keeping trunk" in subjects


def test_blame_names_the_commit_that_last_wrote_these_lines(git_project):
    """The direct answer, against a real repository.

    Walking history reads every version of every file to learn this. Git
    already knows, so the fast path asks rather than recomputes.
    """

    from manuskript.services.git_history_capability import GitHistoryCapability

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("first\nthe scene as it is now\nlast\n", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "wrote the scene")
    wanted = run_git(
        repository, "rev-parse", "HEAD"
    ).stdout.decode().strip()
    scene.write_text(
        "first\nthe scene as it is now\nlast\nadded later\n", encoding="utf-8"
    )
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "added elsewhere")

    blamed = GitHistoryCapability(project_file).blame(
        "book/outline/scene.md", 2, 2
    )

    assert blamed.ok, blamed.error
    assert blamed.value == (wanted,)
