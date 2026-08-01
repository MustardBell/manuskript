from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QMessageBox

from manuskript.services.git_revisions import (
    GitRepository,
    GitRevision,
    GitWorkingTreeStatus,
)
from manuskript.ui.git_revision_dialog import GitRevisionDialog


def make_dialog():
    project_manager = MagicMock()
    project_manager.currentProject = "/repo/book.msk"
    settings = MagicMock()
    settings.revisions = {
        "keep": True,
        "backend": "git",
        "git": {
            "autoCommit": False,
            "taggedOnly": True,
        },
    }
    backend = MagicMock()
    backend.repository = GitRepository(
        root="/repo",
        git_dir="/repo/.git",
        project_file="/repo/book.msk",
        project_paths=("book.msk", "book"),
    )
    backend.status.return_value = GitWorkingTreeStatus(
        head="a" * 40,
        branch="main",
    )
    backend.history.return_value = [
        GitRevision(
            commit_id="a" * 40,
            timestamp=1_700_000_000,
            author_name="Author",
            author_email="author@example.test",
            subject="First milestone",
            tags=("draft-one",),
        )
    ]
    backend.revision_details.return_value = "commit details"
    coordinator = MagicMock()
    coordinator.git_backend.return_value = backend
    dialog = GitRevisionDialog(
        project_manager,
        settings,
        coordinator,
    )
    return dialog, project_manager, settings, coordinator, backend


def test_dialog_defaults_to_tagged_milestones():
    dialog, _manager, settings, _coordinator, backend = (
        make_dialog()
    )

    assert dialog.chkTaggedOnly.isChecked()
    assert dialog.history.topLevelItemCount() == 1
    assert dialog.history.topLevelItem(0).text(2) == "draft-one"
    backend.history.assert_called_with(tagged_only=True)

    dialog.chkTaggedOnly.setChecked(False)

    assert not settings.revisions["git"]["taggedOnly"]
    backend.history.assert_called_with(tagged_only=False)
    dialog.close()


def test_dialog_tags_selected_commit_as_milestone():
    dialog, manager, _settings, coordinator, _backend = (
        make_dialog()
    )

    with patch(
        "manuskript.ui.git_revision_dialog.QInputDialog.getText",
        return_value=("chapter-one", True),
    ):
        dialog._tag()

    coordinator.create_tag.assert_called_once_with(
        manager.currentProject,
        "a" * 40,
        "chapter-one",
    )
    dialog.close()


def test_dialog_restore_uses_owner_mediated_coordinator():
    dialog, manager, _settings, coordinator, _backend = (
        make_dialog()
    )
    coordinator.restore.return_value = True

    with patch(
        "manuskript.ui.git_revision_dialog.QMessageBox.warning",
        return_value=QMessageBox.Yes,
    ):
        dialog._restore()

    coordinator.restore.assert_called_once_with(
        manager,
        "a" * 40,
    )
    dialog.close()
