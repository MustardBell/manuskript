from unittest.mock import MagicMock, patch

from manuskript.services.project_storage import ProjectStorage


def test_storage_passes_explicit_context_to_persistence_facade():
    context = MagicMock()
    storage = ProjectStorage()

    with patch(
        "manuskript.services.project_storage.loadSave.loadProject",
        return_value=[],
    ) as load_project:
        assert storage.load("story.msk", context) == []
    load_project.assert_called_once_with("story.msk", window=context)

    with patch(
        "manuskript.services.project_storage.loadSave.saveProject",
        return_value=True,
    ) as save_project:
        assert storage.save(context)
    save_project.assert_called_once_with(version=None, window=context)


def test_storage_clears_persistence_cache():
    storage = ProjectStorage()

    with patch(
        "manuskript.services.project_storage.loadSave.clearSaveCache"
    ) as clear_cache:
        storage.clear_cache()

    clear_cache.assert_called_once_with()
