import zipfile

import pytest

from manuskript.load_save.format_detection import (
    DetectedProjectFormat,
    ProjectFormatDetector,
    ProjectFormatError,
    ProjectFormatRegistry,
)


def test_detector_reads_plain_text_version_marker(tmp_path):
    project = tmp_path / "story.msk"
    project.write_text("1", encoding="utf-8")

    detected = ProjectFormatDetector().detect(str(project))

    assert detected == DetectedProjectFormat(
        version=1,
        zipped=False,
    )


def test_detector_reads_format_two_marker(tmp_path):
    project = tmp_path / "native.msk"
    project.write_text("2", encoding="utf-8")

    detected = ProjectFormatDetector().detect(str(project))

    assert detected == DetectedProjectFormat(version=2, zipped=False)


def test_detector_reads_zip_marker(tmp_path):
    project = tmp_path / "story.msk"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("MANUSKRIPT", "1")

    detected = ProjectFormatDetector().detect(str(project))

    assert detected == DetectedProjectFormat(
        version=1,
        zipped=True,
    )


def test_unmarked_zip_uses_legacy_format(tmp_path):
    project = tmp_path / "story.msk"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("outline.xml", "<outline/>")

    detected = ProjectFormatDetector().detect(str(project))

    assert detected == DetectedProjectFormat(
        version=0,
        zipped=True,
    )


def test_detector_rejects_invalid_marker(tmp_path):
    project = tmp_path / "story.msk"
    project.write_text("not-a-version", encoding="utf-8")

    with pytest.raises(
        ProjectFormatError,
        match="Invalid project marker",
    ):
        ProjectFormatDetector().detect(str(project))


def test_registry_resolves_only_registered_strategies():
    legacy = object()
    current = object()
    registry = ProjectFormatRegistry(
        {0: legacy, 1: current},
        current_version=1,
    )

    assert registry.resolve() == (1, current)
    assert registry.resolve(0) == (0, legacy)
    with pytest.raises(
        ProjectFormatError,
        match="Unsupported project format version: 42",
    ):
        registry.resolve(42)
