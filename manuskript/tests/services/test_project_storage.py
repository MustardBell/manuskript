from unittest.mock import MagicMock
from pathlib import Path

from PyQt5.QtCore import QObject

from manuskript.domain.persistence import (
    ProjectSaveResult,
)
from manuskript.domain.canonical_project import CanonicalProject
from manuskript.load_save.format_detection import DetectedProjectFormat
from manuskript.load_save.project_codec import EncodedProject
from manuskript.load_save.project_files import ProjectFileReadResult
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.version_1_codec import Version1ProjectCodec
from manuskript.services.project_storage import ProjectStorage
from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import ProjectPersistenceContext
from manuskript.settingsManager import SettingsManager
from manuskript.enums import Outline


def test_storage_routes_v1_through_codec_and_application_adapter():
    context = MagicMock()
    context.project_file = "story.msk"
    context.settings.saveToZip = False
    cache = {}
    file_access = MagicMock()
    file_access.read.return_value = ProjectFileReadResult({})
    file_access.write.return_value = ProjectSaveResult()
    legacy_file_access = MagicMock()
    detector = MagicMock()
    detector.detect.return_value = DetectedProjectFormat(1, False)
    codec = MagicMock()
    canonical = CanonicalProject(format_version=1)
    codec.decode.return_value = canonical
    codec.encode.return_value = EncodedProject(1, ())
    adapter = MagicMock()
    adapter.capture.return_value = canonical
    adapter.moves.return_value = ()
    storage = ProjectStorage(
        file_cache=cache,
        file_access=file_access,
        legacy_file_access=legacy_file_access,
        format_detector=detector,
        version_1_codec=codec,
        application_model_adapter=adapter,
    )

    load_result = storage.load(context)
    save_result = storage.save(context)

    assert load_result.succeeded
    assert save_result.succeeded
    codec.decode.assert_any_call({}, zipped=False)
    adapter.hydrate.assert_called_once_with(canonical, context)
    adapter.capture.assert_called_once_with(context, canonical)
    file_access.write.assert_called_once_with(
        "story.msk", zipped=False, files=(), moves=(), cache=cache
    )


def test_storage_clears_persistence_cache():
    cache = {"outline/scene.md": "text"}
    storage = ProjectStorage(file_cache=cache)
    storage._canonical_project = CanonicalProject(format_version=1)

    storage.clear_cache()

    assert cache == {}
    assert storage.canonical_project is None


def test_storage_instances_do_not_share_file_caches():
    first_cache = {"first.txt": "first"}
    second_cache = {"second.txt": "second"}
    first = ProjectStorage(file_cache=first_cache)
    second = ProjectStorage(file_cache=second_cache)

    first.clear_cache()

    assert first_cache == {}
    assert second_cache == {"second.txt": "second"}


def test_storage_converts_parser_exception_to_fatal_load_result():
    context = MagicMock()
    context.project_file = "broken.msk"
    detector = MagicMock()
    detector.detect.return_value = DetectedProjectFormat(1, False)
    file_access = MagicMock()
    file_access.read.return_value = ProjectFileReadResult({})
    codec = MagicMock()
    codec.decode.side_effect = ValueError("malformed labels")
    storage = ProjectStorage(
        format_detector=detector,
        file_access=file_access,
        version_1_codec=codec,
    )

    result = storage.load(context)

    assert not result.succeeded
    assert result.fatal_errors == (
        "Cannot load project broken.msk: "
        "ValueError: malformed labels",
    )


def test_storage_converts_serializer_exception_to_failed_save_result():
    context = MagicMock()
    context.project_file = "broken.msk"
    adapter = MagicMock()
    adapter.capture.side_effect = TypeError("invalid model value")
    storage = ProjectStorage(application_model_adapter=adapter)

    result = storage.save(context)

    assert not result.succeeded
    assert result.failed_files == ("broken.msk",)


def test_storage_loads_revision_snapshot_from_memory():
    context = MagicMock()
    context.project_file = "book.msk"
    snapshot = MagicMock()
    snapshot.zipped = False
    snapshot.files = {"settings.txt": "{}"}
    codec = MagicMock()
    canonical = CanonicalProject(format_version=1)
    codec.decode.return_value = canonical
    adapter = MagicMock()
    storage = ProjectStorage(
        version_1_codec=codec,
        application_model_adapter=adapter,
    )

    result = storage.load_snapshot(context, snapshot)

    assert not result.succeeded or result.missing_files
    # Missing source sections are recoverable, not a reason to bypass the
    # canonical boundary for revision snapshots.
    codec.decode.assert_called_once_with(snapshot.files, zipped=False)
    adapter.hydrate.assert_called_once_with(canonical, context)


def test_real_v1_storage_round_trip_uses_canonical_boundary_and_preserves_extensions(
    tmp_path,
):
    fixture = (
        Path(__file__).parents[1]
        / "fixtures" / "compatibility" / "v1_complex"
    )
    project_file = tmp_path / "story.msk"
    project_file.write_text("1", encoding="utf-8")
    project_root = tmp_path / "story"
    for source in fixture.rglob("*"):
        if source.is_file():
            target = project_root / source.relative_to(fixture)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    settings = SettingsManager()
    parent = QObject()
    models = ProjectModelFactory().create(parent, settings)
    context = ProjectPersistenceContext(
        project_file=str(project_file), models=models, settings=settings
    )
    storage = ProjectStorage()

    loaded = storage.load(context)
    scene = models.outline.getItemByID("101")
    scene.setData(Outline.text, scene.text() + "\nA deterministic edit.")
    saved = storage.save(context)
    persisted = Version1ProjectFiles().read(
        str(project_file), zipped=False
    ).files
    reopened = Version1ProjectCodec().decode(persisted)

    assert loaded.succeeded
    assert saved.succeeded
    assert storage.canonical_project.format_version == 1
    assert "A deterministic edit." in next(
        item.text for item in reopened.documents() if item.id == "101"
    )
    assert reopened.file("unrecognized.future").content == (
        "opaque future data\n"
    )
    assert reopened.world[0].value("future-field") == "kept"
    assert reopened.plots[0].value("plugin-attribute") == "kept"
