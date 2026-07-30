from unittest.mock import MagicMock

from manuskript.services.revision_coordinator import (
    ProjectRevisionCoordinator,
)


def test_auto_commit_is_optional_for_git_backend():
    backend = MagicMock()
    coordinator = ProjectRevisionCoordinator(
        backend_factory=lambda _project: backend,
    )
    settings = MagicMock()
    settings.revisions = {
        "keep": True,
        "backend": "git",
        "git": {"autoCommit": False},
    }

    result = coordinator.after_project_save(
        "book.msk",
        settings,
    )

    assert result is None
    backend.commit.assert_not_called()


def test_auto_commit_records_project_when_enabled():
    backend = MagicMock()
    backend.commit.return_value = "a" * 40
    coordinator = ProjectRevisionCoordinator(
        backend_factory=lambda _project: backend,
    )
    settings = MagicMock()
    settings.revisions = {
        "keep": True,
        "backend": "git",
        "git": {"autoCommit": True},
    }

    result = coordinator.after_project_save(
        "book.msk",
        settings,
        message="End of chapter",
    )

    assert result == "a" * 40
    backend.commit.assert_called_once_with("End of chapter")


def test_restore_passes_validated_snapshot_to_project_owner():
    backend = MagicMock()
    git_snapshot = MagicMock()
    backend.snapshot.return_value = git_snapshot
    loader = MagicMock()
    loaded = MagicMock()
    loader.load.return_value = loaded
    coordinator = ProjectRevisionCoordinator(
        backend_factory=lambda _project: backend,
        snapshot_loader=loader,
    )
    project_manager = MagicMock()
    project_manager.currentProject = "book.msk"
    project_manager.restoreRevisionSnapshot.return_value = True

    result = coordinator.restore(project_manager, "draft-one")

    assert result
    backend.snapshot.assert_called_once_with("draft-one")
    loader.load.assert_called_once_with(
        "book.msk",
        git_snapshot,
        parent=project_manager.ui.model_parent,
    )
    loader.preserve_revision_configuration.assert_called_once_with(
        loaded,
        project_manager.ui.settings,
    )
    project_manager.restoreRevisionSnapshot.assert_called_once_with(
        loaded
    )
