from dataclasses import replace

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    MetadataField,
    OutlineDocument,
    PreservedProjectFile,
    StructuredMetadataField,
)
from manuskript.load_save.version_2_codec import Version2ProjectCodec


def _project():
    scene = OutlineDocument(
        id="scene-1",
        title="Відкриття",
        kind="scene",
        text="Олена entered [[Places/Kyiv|Києва]].\n",
        metadata=(MetadataField("compile", "true"),),
        structured_metadata=(
            StructuredMetadataField("editor-fold", True),
        ),
    )
    chapter = OutlineDocument(
        id="chapter-1",
        title="Chapter",
        kind="folder",
        text="Chapter notes.\n",
        children=(scene,),
    )
    return CanonicalProject(
        format_version=2,
        metadata=(MetadataField("Title", "Semantic novel"),),
        characters=(CharacterRecord(
            id="17", name="Олена",
            custom_fields=(MetadataField("Language", "uk"),),
        ),),
        outline=(chapter,),
        settings_source="{}",
        unknown_files=(PreservedProjectFile(
            "Research/opaque.bin", b"\x00\x01", "unknown"
        ),),
        structured_metadata=(
            StructuredMetadataField("custom-tool", {"enabled": True}),
            StructuredMetadataField("manuskript.future-option", "kept"),
        ),
    )


def test_format_2_round_trip_assigns_stable_paths_and_preserves_extensions():
    codec = Version2ProjectCodec()

    encoded = dict(codec.encode(_project()).files)
    reopened = codec.decode(encoded)

    assert encoded["MANUSKRIPT"] == "2"
    assert reopened.format_version == 2
    assert tuple(item.id for item in reopened.documents()) == (
        "chapter-1", "scene-1"
    )
    assert all(item.source_path for item in reopened.documents())
    assert reopened.structured_metadata == _project().structured_metadata
    assert reopened.file("Research/opaque.bin").content == b"\x00\x01"
    assert reopened.characters[0].custom_fields == (
        MetadataField("Language", "uk"),
    )


def test_unchanged_format_2_sources_round_trip_exactly():
    codec = Version2ProjectCodec()
    source = dict(codec.encode(_project()).files)
    reopened = codec.decode(source)

    assert dict(codec.encode(reopened).files) == source


def test_changing_one_document_does_not_rewrite_an_untouched_document():
    codec = Version2ProjectCodec()
    source = dict(codec.encode(_project()).files)
    reopened = codec.decode(source)
    chapter, scene = tuple(reopened.documents())
    old_chapter_source = source[chapter.source_path]
    changed_scene = replace(scene, text=scene.text + "Changed.\n")
    changed_project = replace(
        reopened,
        outline=(replace(chapter, children=(changed_scene,)),),
    )

    changed_files = dict(codec.encode(changed_project).files)

    assert changed_files[chapter.source_path] == old_chapter_source
    assert "Changed." in changed_files[scene.source_path]


def test_v2_reader_accepts_legacy_mmd_metadata_without_normalizing_it():
    source = dict(Version2ProjectCodec().encode(_project()).files)
    project_data = source["project.yaml"]
    reopened = Version2ProjectCodec().decode(source)
    scene = tuple(reopened.documents())[1]
    mmd = (
        "title:          Legacy scene\n"
        "ID:             scene-1\n"
        "type:           md\n\n\n"
        "Untouched old metadata.\n"
    )
    source[scene.source_path] = mmd
    source["project.yaml"] = project_data

    decoded = Version2ProjectCodec().decode(source)
    legacy_scene = tuple(decoded.documents())[1]

    assert legacy_scene.source_format == "mmd"
    assert dict(Version2ProjectCodec().encode(decoded).files)[
        scene.source_path
    ] == mmd


def test_v2_validation_reports_duplicate_ids_and_paths():
    codec = Version2ProjectCodec()
    first = OutlineDocument(
        "same", "One", "scene", "", source_path="Manuscript/same.md"
    )
    second = OutlineDocument(
        "same", "Two", "scene", "", source_path="Manuscript/same.md"
    )

    issues = codec.validate(CanonicalProject(
        format_version=2, outline=(first, second)
    ))

    assert any("Duplicate document ID" in issue.message for issue in issues)
    assert any("Duplicate document path" in issue.message for issue in issues)
