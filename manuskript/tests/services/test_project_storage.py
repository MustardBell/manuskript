from unittest.mock import MagicMock, patch

from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.services.project_storage import ProjectStorage


def test_storage_passes_explicit_context_to_persistence_facade():
    context = MagicMock()
    cache = {}
    storage = ProjectStorage(file_cache=cache)
    load_result = ProjectLoadResult()

    with patch(
        "manuskript.services.project_storage.loadSave.loadProject",
        return_value=load_result,
    ) as load_project:
        assert storage.load(context) is load_result
    load_project.assert_called_once_with(context, cache=cache)

    save_result = ProjectSaveResult()
    with patch(
        "manuskript.services.project_storage.loadSave.saveProject",
        return_value=save_result,
    ) as save_project:
        assert storage.save(context) is save_result
    save_project.assert_called_once_with(
        context,
        version=None,
        cache=cache,
    )


def test_storage_clears_persistence_cache():
    cache = {"outline/scene.md": "text"}
    storage = ProjectStorage(file_cache=cache)

    storage.clear_cache()

    assert cache == {}


def test_storage_instances_do_not_share_file_caches():
    first_cache = {"first.txt": "first"}
    second_cache = {"second.txt": "second"}
    first = ProjectStorage(file_cache=first_cache)
    second = ProjectStorage(file_cache=second_cache)

    first.clear_cache()

    assert first_cache == {}
    assert second_cache == {"second.txt": "second"}
