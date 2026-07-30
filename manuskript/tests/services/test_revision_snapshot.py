from copy import deepcopy
from unittest.mock import MagicMock

from manuskript.domain.persistence import ProjectLoadResult
from manuskript.services.git_revisions import GitProjectSnapshot
from manuskript.services.revision_snapshot import RevisionSnapshotLoader


def test_loader_hydrates_detached_models_from_snapshot():
    model_factory = MagicMock()
    models = MagicMock()
    model_factory.create.return_value = models
    storage = MagicMock()
    storage.load_snapshot.return_value = ProjectLoadResult()
    snapshot = GitProjectSnapshot(
        commit_id="a" * 40,
        files={"settings.txt": "{}"},
        zipped=False,
    )
    loader = RevisionSnapshotLoader(
        model_factory=model_factory,
        storage=storage,
    )

    loaded = loader.load("book.msk", snapshot, parent="owner")

    assert loaded.commit_id == snapshot.commit_id
    assert loaded.models is models
    assert loaded.load_result.succeeded
    model_factory.create.assert_called_once()
    assert model_factory.create.call_args.args[0] == "owner"
    storage.load_snapshot.assert_called_once()


def test_loader_preserves_active_revision_backend_configuration():
    current_settings = MagicMock()
    current_settings.revisions = {
        "keep": True,
        "backend": "git",
        "git": {"taggedOnly": True},
    }
    loaded = MagicMock()
    loaded.settings.revisions = {
        "keep": False,
        "backend": "internal",
    }
    expected = deepcopy(current_settings.revisions)

    result = RevisionSnapshotLoader.preserve_revision_configuration(
        loaded,
        current_settings,
    )

    assert result is loaded
    assert loaded.settings.revisions == expected
    assert loaded.settings.revisions is not current_settings.revisions
