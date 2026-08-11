from pathlib import Path
from dataclasses import replace
import zipfile

import pytest

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    MetadataField,
    OutlineDocument,
    PreservedProjectFile,
)
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.version_1_codec import Version1ProjectCodec
from manuskript.load_save.version_2_codec import Version2ProjectCodec
from manuskript.services.project_migration import ProjectMigrationService


def _write_format_one(path, *, zipped=False):
    project = CanonicalProject(
        format_version=1,
        outline=(OutlineDocument(
            "scene-1",
            "Opening",
            "scene",
            "Mara sees [[Characters/Mara]].",
            metadata=(
                MetadataField("ID", "scene-1"),
                MetadataField("title", "Opening"),
                MetadataField("type", "scene"),
            ),
            source_path="outline/scene-1.md",
        ),),
        characters=(CharacterRecord(
            "mara",
            "Mara",
            fields=(MetadataField("name", "Mara"),),
        ),),
        plugin_files=(PreservedProjectFile(
            "plugins/example/data.json", '{"keep": true}', "plugin-owned"
        ),),
    )
    encoded = Version1ProjectCodec().encode(project)
    result = Version1ProjectFiles().write(
        str(path),
        zipped=zipped,
        files=encoded.files,
        moves=(),
        cache={},
        marker_version=1,
    )
    assert result.succeeded


def test_upgrade_writes_validated_format_two_copy_and_leaves_source_untouched(
        tmp_path):
    source = tmp_path / "source.msk"
    destination = tmp_path / "upgraded.msk"
    _write_format_one(source)
    source_marker = source.read_bytes()
    source_files = {
        item.relative_to(tmp_path / "source"): item.read_bytes()
        for item in (tmp_path / "source").rglob("*") if item.is_file()
    }

    report = ProjectMigrationService().upgrade_copy(source, destination)

    assert source.read_bytes() == source_marker
    assert {
        item.relative_to(tmp_path / "source"): item.read_bytes()
        for item in (tmp_path / "source").rglob("*") if item.is_file()
    } == source_files
    assert destination.read_text(encoding="utf-8") == "2"
    reopened_files = Version1ProjectFiles().read(
        str(destination), zipped=False
    ).files
    reopened = Version2ProjectCodec().decode(reopened_files)
    assert reopened.format_version == 2
    assert tuple(reopened.documents())[0].id == "scene-1"
    assert tuple(reopened.documents())[0].source_format == "yaml-frontmatter"
    assert report.succeeded
    assert report.plugin_files_preserved == 1
    assert report.plugin_files_source == 1
    assert "Plugin files: 1 / 1 preserved" in report.render_text()
    assert "Format 1 → Format 2" in report.render_text()


def test_upgrade_converts_legacy_text_documents_to_markdown_paths(tmp_path):
    source = tmp_path / "legacy-folders.msk"
    destination = tmp_path / "upgraded.msk"
    project = CanonicalProject(
        format_version=1,
        outline=(OutlineDocument(
            "chapter-1",
            "Chapter",
            "folder",
            "Chapter notes.",
            metadata=(
                MetadataField("ID", "chapter-1"),
                MetadataField("title", "Chapter"),
                MetadataField("type", "folder"),
            ),
            source_path="outline/chapter/folder.txt",
            children=(OutlineDocument(
                "scene-1",
                "Opening",
                "scene",
                "Opening text.",
                metadata=(
                    MetadataField("ID", "scene-1"),
                    MetadataField("title", "Opening"),
                    MetadataField("type", "scene"),
                ),
                source_path="outline/chapter/opening.md",
            ),),
        ),),
    )
    encoded = Version1ProjectCodec().encode(project)
    written = Version1ProjectFiles().write(
        str(source),
        zipped=False,
        files=encoded.files,
        moves=(),
        cache={},
        marker_version=1,
    )
    assert written.succeeded

    report = ProjectMigrationService().upgrade_copy(source, destination)

    files = Version1ProjectFiles().read(str(destination), zipped=False).files
    reopened = Version2ProjectCodec().decode(files)
    documents = tuple(reopened.documents())
    assert report.succeeded
    assert tuple(item.id for item in documents) == ("chapter-1", "scene-1")
    assert documents[0].source_path == "outline/chapter/folder.md"
    assert documents[1].source_path == "outline/chapter/opening.md"
    assert all(item.source_path.casefold().endswith(".md") for item in documents)


def test_upgrade_refuses_same_or_existing_destination_before_writing(tmp_path):
    source = tmp_path / "source.msk"
    _write_format_one(source)
    service = ProjectMigrationService()

    with pytest.raises(ValueError, match="separate copy"):
        service.upgrade_copy(source, source)
    destination = tmp_path / "existing.msk"
    destination.write_text("do not replace", encoding="utf-8")
    with pytest.raises(FileExistsError):
        service.upgrade_copy(source, destination)
    assert destination.read_text(encoding="utf-8") == "do not replace"


def test_upgrade_refuses_non_format_one_source(tmp_path):
    source = tmp_path / "already-v2.msk"
    source.write_text("2", encoding="utf-8")

    with pytest.raises(ValueError, match="Format 1"):
        ProjectMigrationService().upgrade_copy(
            source, tmp_path / "copy.msk"
        )


def test_upgrade_preserves_archive_packaging(tmp_path):
    source = tmp_path / "source.msk"
    destination = tmp_path / "upgraded.msk"
    _write_format_one(source, zipped=True)

    report = ProjectMigrationService().upgrade_copy(source, destination)

    assert report.succeeded
    assert zipfile.is_zipfile(destination)
    files = Version1ProjectFiles().read(
        str(destination), zipped=True
    ).files
    assert Version2ProjectCodec().decode(files).format_version == 2


def test_upgrade_refuses_to_write_when_preservation_validation_detects_loss(
        tmp_path):
    class LossyVersion2Codec(Version2ProjectCodec):
        def decode(self, files, *, zipped=False):
            project = super().decode(files, zipped=zipped)
            return replace(project, plugin_files=())

    source = tmp_path / "source.msk"
    destination = tmp_path / "upgraded.msk"
    _write_format_one(source)

    with pytest.raises(ValueError, match="preservation validation"):
        ProjectMigrationService(
            version_2_codec=LossyVersion2Codec()
        ).upgrade_copy(source, destination)

    assert not destination.exists()
    assert not (tmp_path / "upgraded").exists()
