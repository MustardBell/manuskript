import pytest

from manuskript.domain.project_paths import (
    normalize_project_path,
    project_path_on_disk,
)


def test_project_paths_have_one_cross_platform_representation(tmp_path):
    assert normalize_project_path("outline/chapter/scene.md") == (
        "outline/chapter/scene.md"
    )
    assert normalize_project_path(r"outline\chapter\scene.md") == (
        "outline/chapter/scene.md"
    )
    assert project_path_on_disk(
        str(tmp_path),
        "outline/chapter/scene.md",
    ) == str(tmp_path / "outline" / "chapter" / "scene.md")


@pytest.mark.parametrize(
    "path",
    ("../outside", "/outside", r"C:\outside", ""),
)
def test_project_paths_reject_absolute_and_escaping_names(path):
    with pytest.raises(ValueError, match="escapes its storage root"):
        normalize_project_path(path)
