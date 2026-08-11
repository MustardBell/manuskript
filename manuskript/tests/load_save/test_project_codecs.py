import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from manuskript.domain.canonical_project import MetadataField
from manuskript.domain.project_features import (
    MorphologyPersistenceDecorator,
    PersistenceDecorator,
    PersistenceLevel,
    V1PersistenceStrategy,
    compatibility_strategy,
)
from manuskript.load_save.project_codec import ProjectCodecRegistry
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.legacy_archive import Version0ProjectArchive
from manuskript.load_save.version_0_codec import Version0ProjectCodec
from manuskript.load_save.version_1_codec import Version1ProjectCodec


CORPUS = Path(__file__).parents[1] / "fixtures" / "compatibility"


def _fixture_files(name):
    root = CORPUS / name
    files = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        if path.suffix.lower() in (".xml", ".opml"):
            files[relative] = content
        else:
            files[relative] = content.decode("utf-8")
    # Project archives store a marker without a presentation newline.
    if "MANUSKRIPT" in files:
        files["MANUSKRIPT"] = files["MANUSKRIPT"].strip()
    return files


def test_codecs_and_canonical_domain_import_without_qt():
    script = """
import sys
from manuskript.load_save.version_0_codec import Version0ProjectCodec
from manuskript.load_save.version_1_codec import Version1ProjectCodec
assert not any(name == 'PyQt5' or name.startswith('PyQt5.') for name in sys.modules)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).parents[3])

    completed = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("fixture", ("v1_minimal", "v1_complex"))
def test_v1_corpus_round_trips_unchanged_sources_exactly(fixture):
    source = _fixture_files(fixture)
    codec = Version1ProjectCodec()

    project = codec.decode(source, zipped=False)
    encoded = dict(codec.encode(project).files)
    reopened = codec.decode(encoded, zipped=False)

    assert encoded == source
    assert reopened == project


def test_v1_complex_fixture_preserves_duplicates_unknowns_and_provenance():
    project = Version1ProjectCodec().decode(_fixture_files("v1_complex"))

    assert project.metadata[-1] == MetadataField(
        "Unknown Header", "preserved"
    )
    assert [item.value for item in project.characters[0].custom_fields] == [
        "uk", "Лена", "Оленка"
    ]
    assert project.characters[0].source_path.endswith("renamed-file.txt")
    assert [item.path for item in project.plugin_files] == [
        "plugins/example/data.json"
    ]
    assert [item.path for item in project.unknown_files] == [
        "unrecognized.future"
    ]
    assert tuple(document.id for document in project.documents()) == (
        "100", "101", "102"
    )


def test_v1_crlf_sources_parse_semantically_and_round_trip_exactly():
    source = {
        path: (
            content.replace("\n", "\r\n")
            if isinstance(content, str) else content
        )
        for path, content in _fixture_files("v1_complex").items()
    }
    project = Version1ProjectCodec().decode(source)

    assert project.metadata[-1] == MetadataField(
        "Unknown Header", "preserved"
    )
    assert [item.value for item in project.characters[0].custom_fields] == [
        "uk", "Лена", "Оленка"
    ]
    assert tuple(document.id for document in project.documents()) == (
        "100", "101", "102"
    )
    assert dict(Version1ProjectCodec().encode(project).files) == source


def test_v1_archive_uses_the_same_canonical_codec(tmp_path):
    source = _fixture_files("v1_complex")
    archive = tmp_path / "complex.msk"
    access = Version1ProjectFiles()

    written = access.write(
        str(archive), zipped=True, files=tuple(source.items()),
        moves=(), cache={},
    )
    read = access.read(str(archive), zipped=True)
    project = Version1ProjectCodec().decode(read.files, zipped=True)

    assert written.succeeded
    assert project.zipped
    assert tuple(item.id for item in project.characters) == ("17",)
    assert dict(Version1ProjectCodec().encode(project).files) == source


def test_damaged_project_is_recoverable_and_never_silently_discarded():
    source = _fixture_files("v1_damaged")
    codec = Version1ProjectCodec()

    project = codec.decode(source)

    assert any("world.opml" in issue.message for issue in project.issues)
    assert any("plots.xml" in issue.message for issue in project.issues)
    assert any("recovery ID" in issue.message for issue in project.issues)
    assert dict(codec.encode(project).files) == source


def test_large_v1_project_decodes_without_application_models():
    files = _fixture_files("v1_minimal")
    files.pop("outline/00-Opening.md")
    for index in range(1200):
        files["outline/{:04d}-Scene.md".format(index)] = (
            "title: Scene {index}\n"
            "ID: scene-{index}\n"
            "type: md\n\n\nText {index}."
        ).format(index=index)

    project = Version1ProjectCodec().decode(files)

    assert len(tuple(project.documents())) == 1200


def test_v0_corpus_is_read_and_round_tripped_without_unpickling_settings():
    source = _fixture_files("v0_minimal")
    codec = Version0ProjectCodec()

    project = codec.decode(source)

    assert project.legacy_models[0].rows[0][0].text == "Legacy"
    assert project.file("settings.pickle").content == (
        "intentionally-not-unpickled\n"
    )
    assert dict(codec.encode(project).files) == source


def test_v0_archive_materializes_into_the_qt_free_model(tmp_path):
    source = _fixture_files("v0_minimal")
    archive_path = tmp_path / "legacy.msk"
    archive = Version0ProjectArchive()
    archive.write(
        str(archive_path),
        [(content, path) for path, content in source.items()],
    )

    project = Version0ProjectCodec().decode(archive.read(str(archive_path)))

    assert project.format_version == 0
    assert project.legacy_models[0].rows[0][0].text == "Legacy"


def test_codec_registry_resolves_formats_without_ui_handlers():
    registry = ProjectCodecRegistry((
        Version0ProjectCodec(), Version1ProjectCodec()
    ))

    assert registry.versions == (0, 1)
    assert registry.resolve(1).format_version == 1
    with pytest.raises(ValueError, match="Unsupported project format"):
        registry.resolve(42)


def test_features_negotiate_structured_compatibility_not_version_checks():
    strategy = compatibility_strategy(1)

    links = strategy.support("references.write")
    assertions = strategy.support("story.assertions")
    assertion_write = strategy.support("assertions.write")
    entity_read = strategy.support("entities.read")
    entity_write = strategy.support("entities.write")
    project_files = strategy.support("plugins.project-files")
    timeline_write = strategy.support("timeline.write")
    rules_execute = strategy.support("rules.execute")
    workflow_write = strategy.support("workflow.write")

    assert links.persistence_level is PersistenceLevel.COMPATIBLE_ENCODING
    assert links.old_client_save_safe
    assert assertions.persistence_level is PersistenceLevel.OVERLAY
    assert not assertions.old_client_save_safe
    assert (
        assertion_write.persistence_level
        is PersistenceLevel.COMPATIBLE_ENCODING
    )
    assert assertion_write.writable
    assert assertion_write.old_client_save_safe
    assert timeline_write.persistence_level is PersistenceLevel.COMPATIBLE_ENCODING
    assert timeline_write.writable and timeline_write.old_client_save_safe
    assert rules_execute.readable and rules_execute.old_client_save_safe
    assert not workflow_write.supported
    assert entity_read.persistence_level is PersistenceLevel.DERIVED
    assert entity_read.readable and not entity_read.writable
    assert not entity_write.supported
    assert not project_files.old_client_save_safe


def test_v2_negotiates_native_entity_morphology_without_format_checks():
    support = compatibility_strategy(2).support("morphology.entities")

    assert support.persistence_level is PersistenceLevel.NATIVE
    assert support.readable
    assert support.writable


def test_v2_negotiates_native_revision_workflow_metadata():
    support = compatibility_strategy(2).support("workflow.write")

    assert support.persistence_level is PersistenceLevel.NATIVE
    assert support.readable and support.writable


def test_persistence_decorator_cannot_shadow_authoritative_base_fields():
    base = V1PersistenceStrategy()
    existing = base.support("outline.write")

    class InvalidDecorator(PersistenceDecorator):
        namespace = "outline"

    with pytest.raises(ValueError, match="cannot shadow"):
        InvalidDecorator(base, (existing,))
