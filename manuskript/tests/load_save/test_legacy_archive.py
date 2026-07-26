import zipfile
from unittest.mock import MagicMock, patch

import pytest

from manuskript.load_save.legacy_archive import (
    LegacyArchiveReadError,
    LegacyArchiveWriteError,
    Version0ProjectArchive,
)
from manuskript.load_save import version_0


def test_legacy_archive_reads_files_and_skips_directories(tmp_path):
    project = tmp_path / "legacy.msk"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("folder/", "")
        archive.writestr("outline.xml", b"<outline/>")

    files = Version0ProjectArchive().read(str(project))

    assert files == {"outline.xml": b"<outline/>"}


def test_legacy_archive_atomically_writes_readable_project(tmp_path):
    project = tmp_path / "legacy.msk"
    archive = Version0ProjectArchive()

    archive.write(
        str(project),
        [
            (b"<outline/>", "outline.xml"),
            ("settings", "settings.txt"),
        ],
    )

    assert archive.read(str(project)) == {
        "outline.xml": b"<outline/>",
        "settings.txt": b"settings",
    }
    assert list(tmp_path.glob(".manuskript-legacy-*.tmp")) == []


def test_legacy_archive_reports_corrupt_zip(tmp_path):
    project = tmp_path / "legacy.msk"
    project.write_bytes(b"not a zip")

    with pytest.raises(
        LegacyArchiveReadError,
        match="Cannot read legacy project",
    ):
        Version0ProjectArchive().read(str(project))


def test_legacy_archive_preserves_original_when_replacement_fails(
    tmp_path,
):
    project = tmp_path / "legacy.msk"
    original = b"original project"
    project.write_bytes(original)
    archive = Version0ProjectArchive()

    with patch.object(
        zipfile.ZipFile,
        "writestr",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(
            LegacyArchiveWriteError,
            match="Cannot save legacy project",
        ):
            archive.write(
                str(project),
                [(b"content", "outline.xml")],
            )

    assert project.read_bytes() == original
    assert list(tmp_path.glob(".manuskript-legacy-*.tmp")) == []


def test_legacy_handler_converts_archive_failures_to_results():
    context = MagicMock()
    context.project_file = "legacy.msk"
    archive = MagicMock()
    archive.read.side_effect = LegacyArchiveReadError("unreadable")

    load_result = version_0.loadProject(context, archive=archive)

    assert not load_result.succeeded
    assert load_result.fatal_errors == ("unreadable",)

    archive.write.side_effect = LegacyArchiveWriteError("unwritable")
    with patch.object(
        version_0,
        "saveStandardItemModelXML",
        return_value=b"<model/>",
    ):
        save_result = version_0.saveProject(
            context,
            archive=archive,
        )

    assert not save_result.succeeded
    assert save_result.failed_files == ("legacy.msk",)
