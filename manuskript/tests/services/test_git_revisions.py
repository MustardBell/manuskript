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
        "book/outline/scene.md", [(2, 2)]
    )

    assert blamed.ok, blamed.error
    assert [origin.commit_id for origin in blamed.value] == [wanted]
    assert not blamed.value[0].uncommitted


def test_blame_is_parsed_at_whatever_width_the_repository_hashes_at():
    """A parser that checks for forty characters is not parsing Git.

    SHA-256 repositories identify objects in sixty-four characters. The old
    parser kept any line of four fields whose first was forty long, so in
    such a repository it matched nothing, the capability answered with an
    empty tuple, and the panel reported a successful search that had found
    the passage nowhere.
    """

    from manuskript.services.git_history_capability import (
        _parse_incremental_blame,
    )

    wide = "a1" * 32  # sixty-four characters, as SHA-256 writes them
    payload = (
        "{} 1 1 2\n"
        "author Revision Tester\n"
        "summary wrote the scene\n"
        "filename book/outline/scene.md\n"
    ).format(wide).encode("utf-8")

    origins = _parse_incremental_blame(payload)

    assert [origin.commit_id for origin in origins] == [wide]


def test_blame_parsing_ignores_records_a_later_git_might_add():
    """Unknown tags are skipped, which is what the format asks of readers."""

    from manuskript.services.git_history_capability import (
        _parse_incremental_blame,
    )

    payload = (
        "b" * 40 + " 1 1 1\n"
        "author Revision Tester\n"
        "something-git-invented later\n"
        "boundary\n"
        "filename book/outline/scene.md\n"
    ).encode("utf-8")

    (origin,) = _parse_incremental_blame(payload)

    assert origin.commit_id == "b" * 40
    assert origin.boundary


def test_blame_answers_about_every_range_in_one_call(git_project):
    """A passage a writer used twice is two questions and one command."""

    from manuskript.services.git_history_capability import GitHistoryCapability

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("the refrain\nsomething else\n", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "wrote the refrain")
    first = run_git(repository, "rev-parse", "HEAD").stdout.decode().strip()
    scene.write_text(
        "the refrain\nsomething else\nthe refrain\n", encoding="utf-8"
    )
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "used it again")
    second = run_git(repository, "rev-parse", "HEAD").stdout.decode().strip()

    blamed = GitHistoryCapability(project_file).blame(
        "book/outline/scene.md", [(1, 1), (3, 3)]
    )

    assert blamed.ok, blamed.error
    assert {origin.commit_id for origin in blamed.value} == {first, second}


def test_blame_reports_uncommitted_lines_as_uncommitted_not_as_a_hash(
    git_project,
):
    """Git's all-zero identity is not a commit and must never be copyable.

    In a SHA-1 repository it is forty zeroes, which passed every test the
    old parser made of a hash, so "Not Committed Yet" was offered to a
    reader as the commit their prose came from.
    """

    from manuskript.services.git_history_capability import GitHistoryCapability

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("committed line\n", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "wrote a line")
    scene.write_text("committed line\njust typed this\n", encoding="utf-8")

    blamed = GitHistoryCapability(project_file).blame(
        "book/outline/scene.md", [(2, 2)]
    )

    assert blamed.ok, blamed.error
    (origin,) = blamed.value
    assert origin.uncommitted
    assert origin.commit_id == ""


def test_blame_refuses_a_file_in_the_middle_of_a_merge(git_project):
    """Conflicted text is two drafts and three markers, not anyone's prose.

    Git blames it happily, attributing the markers to nobody and each side
    to the history it came from. Worse, normalization discards punctuation,
    so prose either side of a "=======" reads as one continuous passage that
    no commit ever contained -- and the search would report provenance for
    it confidently.
    """

    from manuskript.services.git_history_capability import (
        GIT_UNMERGED,
        GitHistoryCapability,
    )

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("base\n", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "base")
    trunk = run_git(
        repository, "rev-parse", "--abbrev-ref", "HEAD"
    ).stdout.decode().strip()
    run_git(repository, "checkout", "-q", "-b", "side")
    scene.write_text("theirs\n", encoding="utf-8")
    run_git(repository, "commit", "-q", "-am", "theirs")
    run_git(repository, "checkout", "-q", trunk)
    scene.write_text("ours\n", encoding="utf-8")
    run_git(repository, "commit", "-q", "-am", "ours")
    subprocess.run(  # conflicts on purpose, so it must not be checked
        ["git", "-C", str(repository), "merge", "side"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )

    blamed = GitHistoryCapability(project_file).blame(
        "book/outline/scene.md", [(1, 5)]
    )

    assert not blamed.ok
    assert blamed.error.code == GIT_UNMERGED


def test_blame_distinguishes_a_root_from_a_history_it_cannot_see_past(
    git_project, tmp_path
):
    """Git calls both a boundary, and only one of them is certain.

    A root commit means "nothing precedes this". A shallow clone's floor
    means "you were not given what precedes this". Reporting them alike
    either teaches a reader to doubt a certain answer or hides an uncertain
    one.
    """

    from manuskript.services.git_history_capability import GitHistoryCapability

    repository, project_file = git_project
    scene = repository / "book" / "outline" / "scene.md"
    scene.write_text("the oldest words\nand more\n", encoding="utf-8")
    run_git(repository, "add", str(scene))
    run_git(repository, "commit", "-m", "wrote more")

    # "settings.txt" has not changed since the project's first commit, so
    # blaming it reaches a real root: nothing precedes it, and Git says
    # boundary because there is genuinely nothing there.
    root = GitHistoryCapability(project_file).blame(
        "book/settings.txt", [(1, 1)]
    )

    assert root.ok, root.error
    assert root.value[0].boundary
    assert not root.value[0].truncated

    # And a commit Git can see past is not a boundary at all.
    whole = GitHistoryCapability(project_file).blame(
        "book/outline/scene.md", [(1, 1)]
    )

    assert whole.ok, whole.error
    assert not whole.value[0].boundary

    clone = tmp_path.parent / "shallow"
    run_git(
        tmp_path, "clone", "-q", "--depth", "1",
        "file://{}".format(repository), str(clone),
    )
    shallow = GitHistoryCapability(str(clone / "book.msk")).blame(
        "book/outline/scene.md", [(1, 1)]
    )

    assert shallow.ok, shallow.error
    assert shallow.value[0].boundary
    assert shallow.value[0].truncated


def test_git_is_not_answered_from_whatever_repository_the_shell_pointed_at(
        monkeypatch):
    """GIT_DIR beats git -C, so a reader's shell could redirect everything.

    Silently, and with plausible results: a search would answer from the
    wrong repository rather than fail in a way anyone would notice.
    """

    from manuskript.services.git_revisions import GitCommandRunner

    monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/somewhere/else")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", "/")
    monkeypatch.setenv("HOME", "/home/writer")

    environment = GitCommandRunner(executable="/usr/bin/git").environment()

    assert "GIT_DIR" not in environment
    assert "GIT_WORK_TREE" not in environment
    assert "GIT_CEILING_DIRECTORIES" not in environment
    # And the rest of the reader's environment is left alone.
    assert environment["HOME"] == "/home/writer"


def test_reading_history_never_reaches_the_network_or_asks_a_question():
    """A partly-cloned repository will fetch a missing object mid-search.

    That turns "where did this paragraph come from" into a request that can
    wait on a network, a credential helper, or nothing at all -- which is a
    search that appears to hang with nothing on stderr, because stderr is a
    pipe nobody is reading.
    """

    from manuskript.services.git_revisions import GitCommandRunner

    environment = GitCommandRunner(executable="/usr/bin/git").environment()

    assert environment["GIT_NO_LAZY_FETCH"] == "1"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"


def test_a_caller_that_needs_its_own_variable_still_gets_a_clean_base(
        monkeypatch):
    """The commit path sets GIT_INDEX_FILE and wants none of the others."""

    from manuskript.services.git_revisions import GitCommandRunner

    monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")

    environment = GitCommandRunner(executable="/usr/bin/git").environment(
        {"GIT_INDEX_FILE": "/tmp/index"}
    )

    assert environment["GIT_INDEX_FILE"] == "/tmp/index"
    assert "GIT_DIR" not in environment


def test_a_wedged_git_command_is_given_up_on_rather_than_waited_for():
    """The Stop button cannot interrupt subprocess.run, so this bounds it.

    Not a ration on how much history may be searched -- the search reads as
    many commits as it likes. This bounds one external process, because a
    command that never returns is indistinguishable from a search still
    working.
    """

    import subprocess

    from manuskript.services.git_revisions import GitCommandRunner, GitTimedOut

    def never_returns(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])

    runner = GitCommandRunner(
        executable="/usr/bin/git", run=never_returns, timeout=5
    )

    with pytest.raises(GitTimedOut, match="5 seconds"):
        runner.execute(("log", "--oneline"))
