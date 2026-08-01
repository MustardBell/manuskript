from unittest.mock import MagicMock

from manuskript.services.project_history import ProjectHistory


def test_project_history_tracks_last_project_and_autoload():
    settings = MagicMock()
    history = ProjectHistory(settings)

    history.remember_last_project("story.msk")
    history.clear_last_project()

    assert settings.setValue.call_args_list[0].args == (
        "lastProject",
        "story.msk",
    )
    assert settings.setValue.call_args_list[1].args == (
        "lastProject",
        "",
    )


def test_project_history_reads_welcome_preferences():
    settings = MagicMock()
    settings.value.side_effect = (
        True,
        "story.msk",
        "/tmp/projects",
    )
    settings.contains.return_value = True
    history = ProjectHistory(settings)

    assert history.auto_load_values() == (True, "story.msk")
    assert history.last_accessed_directory() == "/tmp/projects"


def test_project_history_deduplicates_and_limits_recent_files():
    settings = MagicMock()
    settings.contains.return_value = True
    settings.value.return_value = [
        "older.msk",
        "story.msk",
    ] + [f"{index}.msk" for index in range(12)]
    history = ProjectHistory(settings)

    history.remember_recent_file("story.msk")

    key, files = settings.setValue.call_args.args
    assert key == "recentFiles"
    assert files[0] == "story.msk"
    assert files.count("story.msk") == 1
    assert len(files) == 10
