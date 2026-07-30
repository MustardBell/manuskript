import shutil
import subprocess
from pathlib import Path


def run_git(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def test_git_revision_restore_replaces_live_project_without_checkout(
    MWNoProject,
    tmp_path,
):
    source_root = Path("sample-projects")
    project_file = tmp_path / "book.msk"
    project_directory = tmp_path / "book"
    shutil.copyfile(
        source_root / "book-of-acts.msk",
        project_file,
    )
    shutil.copytree(
        source_root / "book-of-acts",
        project_directory,
    )
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.name", "Restore Tester")
    run_git(
        tmp_path,
        "config",
        "user.email",
        "restore@example.test",
    )
    run_git(tmp_path, "add", "book.msk", "book")
    run_git(tmp_path, "commit", "-q", "-m", "Initial project")
    initial_commit = run_git(
        tmp_path,
        "rev-parse",
        "HEAD",
    ).stdout.decode().strip()

    scene_file = (
        project_directory
        / "outline"
        / "0-Jerusalem"
        / "0-Chapter_1"
        / "0-Introduction.md"
    )
    marker = "\n\nRESTORE-INTEGRATION-MARKER\n"
    scene_file.write_text(
        scene_file.read_text(encoding="utf-8") + marker,
        encoding="utf-8",
    )
    run_git(tmp_path, "add", "book")
    run_git(tmp_path, "commit", "-q", "-m", "Change scene")

    assert MWNoProject.projectManager.loadProject(str(project_file))
    MWNoProject.settingsManager.saveOnQuit = False
    MWNoProject.settingsManager.revisions.update({
        "keep": True,
        "backend": "git",
    })
    before_restore = [
        item.text()
        for item in MWNoProject.mdlOutline.searchableItems()
    ]
    assert any("RESTORE-INTEGRATION-MARKER" in text
               for text in before_restore)

    restored = MWNoProject.revisionCoordinator.restore(
        MWNoProject.projectManager,
        initial_commit,
    )

    assert restored
    assert MWNoProject.currentProject == str(project_file)
    after_restore = [
        item.text()
        for item in MWNoProject.mdlOutline.searchableItems()
    ]
    assert not any("RESTORE-INTEGRATION-MARKER" in text
                   for text in after_restore)
    assert "RESTORE-INTEGRATION-MARKER" not in scene_file.read_text(
        encoding="utf-8"
    )
    assert MWNoProject.settingsManager.revisions["backend"] == "git"
    assert MWNoProject.projectManager.session.is_open
