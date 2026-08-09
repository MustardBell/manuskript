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


def test_load_snapshot_takes_plain_data_and_returns_the_model():
    """The coordinator knows Git and snapshots; it never receives a
    project manager, so nothing can reach through it to one.
    """
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
    settings = MagicMock()
    parent = object()

    result = coordinator.load_snapshot(
        "book.msk", "draft-one", settings, parent=parent,
    )

    assert result is loaded
    backend.snapshot.assert_called_once_with("draft-one")
    loader.load.assert_called_once_with(
        "book.msk",
        git_snapshot,
        parent=parent,
    )
    loader.preserve_revision_configuration.assert_called_once_with(
        loaded,
        settings,
    )


def test_restore_revision_is_orchestrated_by_the_manager():
    """restoreRevision asks the coordinator for the snapshot, then goes
    through the manager's own validated-replacement path.
    """
    from manuskript.projectManager import ProjectManager

    manager = ProjectManager.__new__(ProjectManager)
    manager.revision_coordinator = MagicMock()
    loaded = MagicMock()
    manager.revision_coordinator.load_snapshot.return_value = loaded
    manager.ui = MagicMock()
    manager.settings = MagicMock()
    manager.model_parent = MagicMock()
    manager.session = MagicMock()
    manager.session.path = "book.msk"
    manager.restoreRevisionSnapshot = MagicMock(return_value=True)

    assert manager.restoreRevision("draft-one")

    manager.revision_coordinator.load_snapshot.assert_called_once_with(
        manager.currentProject,
        "draft-one",
        manager.settings,
        parent=manager.model_parent,
    )
    manager.restoreRevisionSnapshot.assert_called_once_with(loaded)


def test_commit_revision_saves_first_and_commits_the_saved_project():
    from manuskript.projectManager import ProjectManager

    manager = ProjectManager.__new__(ProjectManager)
    backend = MagicMock()
    backend.commit.return_value = "b" * 40
    manager.revision_coordinator = MagicMock()
    manager.revision_coordinator.git_backend.return_value = backend
    manager.ui = MagicMock()
    manager.session = MagicMock()
    manager.session.path = "book.msk"
    manager.saveDatas = MagicMock(return_value=True)

    result = manager.commitRevision("Chapter complete")

    assert result == "b" * 40
    # Saving is what guarantees the pending text is written, so committing
    # asks for a save rather than flushing on its own. It used to do both,
    # which is why every other way of saving could forget.
    manager.ui.flush_pending_edits.assert_not_called()
    manager.saveDatas.assert_called_once_with(record_revision=False)
    backend.commit.assert_called_once_with("Chapter complete")
