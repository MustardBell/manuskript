import os

import pytest
from PyQt5.QtCore import QSettings

from manuskript.services.theme_repository import ThemeRepository


def write_theme(path, name):
    settings = QSettings(str(path), QSettings.IniFormat)
    settings.setValue("Name", name)
    settings.sync()


def make_repository(tmp_path):
    application = tmp_path / "application"
    writable = tmp_path / "writable"
    application.mkdir()
    writable.mkdir()
    return ThemeRepository(
        theme_directories=(str(application), str(writable)),
        writable_directory=str(writable),
        application_directory=str(application),
    ), application, writable


def test_theme_repository_discovers_editability_by_storage_root(
    tmp_path,
):
    repository, application, writable = make_repository(tmp_path)
    built_in = application / "default.theme"
    custom = writable / "custom.theme"
    write_theme(built_in, "Default")
    write_theme(custom, "Custom")

    themes = repository.list()

    assert [(theme.name, theme.editable) for theme in themes] == [
        ("Default", False),
        ("Custom", True),
    ]


def test_theme_repository_creates_unique_safe_names(tmp_path):
    repository, _application, writable = make_repository(tmp_path)

    first = repository.create("../new theme", "New theme")
    second = repository.create("../new theme", "New theme")

    assert os.path.dirname(first) == str(writable)
    assert os.path.basename(first) == "new_theme.theme"
    assert os.path.basename(second) == "new_theme_1.theme"


def test_theme_repository_saves_loads_and_removes_custom_theme(
    tmp_path,
):
    repository, _application, _writable = make_repository(tmp_path)
    path = repository.create("custom", "Custom")
    data = repository.load(path)
    data["Background/Color"] = "#123456"

    repository.save(path, data)

    assert repository.load(path)["Background/Color"] == "#123456"
    repository.remove(path)
    assert not os.path.exists(path)


def test_theme_repository_protects_built_in_themes(tmp_path):
    repository, application, _writable = make_repository(tmp_path)
    built_in = application / "default.theme"
    write_theme(built_in, "Default")

    with pytest.raises(PermissionError):
        repository.save(str(built_in), {"Name": "Changed"})
    with pytest.raises(PermissionError):
        repository.remove(str(built_in))
