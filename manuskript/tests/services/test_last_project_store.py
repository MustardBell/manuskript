from unittest.mock import MagicMock

from manuskript.services.last_project_store import LastProjectStore


def test_last_project_store_uses_injected_settings_backend():
    settings = MagicMock()
    store = LastProjectStore(settings)

    store.remember("story.msk")
    store.clear()

    assert settings.setValue.call_args_list[0].args == (
        "lastProject",
        "story.msk",
    )
    assert settings.setValue.call_args_list[1].args == (
        "lastProject",
        "",
    )
