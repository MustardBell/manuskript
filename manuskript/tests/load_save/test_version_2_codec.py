from dataclasses import replace

import pytest

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    EntityRecord,
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
        entities=(EntityRecord(
            document=OutlineDocument(
                id="entity-olena",
                title="Олена Коваль",
                kind="entity",
                text="Entity notes.\n",
                source_path="Characters/Олена Коваль.md",
                structured_metadata=(
                    StructuredMetadataField("obsidian-cssclasses", ["person"]),
                ),
            ),
            entity_type="character",
            aliases=("Олена", "Олени"),
            metadata=(
                StructuredMetadataField("language", "uk"),
            ),
        ),),
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
        "chapter-1", "scene-1", "entity-olena"
    )
    assert all(item.source_path for item in reopened.documents())
    assert reopened.structured_metadata == _project().structured_metadata
    assert reopened.file("Research/opaque.bin").content == b"\x00\x01"
    assert reopened.characters[0].custom_fields == (
        MetadataField("Language", "uk"),
    )
    assert reopened.entities[0].aliases == ("Олена", "Олени")
    assert reopened.entities[0].metadata == (
        StructuredMetadataField("language", "uk"),
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
    chapter, scene, entity_document = tuple(reopened.documents())
    old_chapter_source = source[chapter.source_path]
    changed_scene = replace(scene, text=scene.text + "Changed.\n")
    changed_project = replace(
        reopened,
        outline=(replace(chapter, children=(changed_scene,)),),
    )

    changed_files = dict(codec.encode(changed_project).files)

    assert changed_files[chapter.source_path] == old_chapter_source
    assert "Changed." in changed_files[scene.source_path]
    assert changed_files[entity_document.source_path] == source[
        entity_document.source_path
    ]


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


def test_ordinary_obsidian_markdown_is_preserved_without_becoming_a_document():
    codec = Version2ProjectCodec()
    source = dict(codec.encode(_project()).files)
    source["README.md"] = "---\ntags: [vault]\n---\nOrdinary note.\n"

    reopened = codec.decode(source)

    assert all(document.source_path != "README.md" for document in reopened.documents())
    assert reopened.file("README.md").content == source["README.md"]
    assert not any(
        issue.source.path == "README.md" for issue in reopened.issues
    )


def test_stable_entity_id_recovers_an_obsidian_file_rename():
    codec = Version2ProjectCodec()
    source = dict(codec.encode(_project()).files)
    entity = codec.decode(source).entities[0]
    old_path = entity.document.source_path
    new_path = "Characters/Олена перейменована.md"
    source[new_path] = source.pop(old_path)

    reopened = codec.decode(source)

    assert reopened.entities[0].id == entity.id
    assert reopened.entities[0].document.source_path == new_path
    assert any(
        "stable ID recovered" in issue.message for issue in reopened.issues
    )


def test_v2_validation_and_encoding_reject_paths_outside_the_project():
    codec = Version2ProjectCodec()
    unsafe = replace(
        _project(),
        outline=(OutlineDocument(
            "escape", "Escape", "scene", "", source_path="../escape.md"
        ),),
    )

    issues = codec.validate(unsafe)

    assert any("escapes its storage root" in issue.message for issue in issues)
    with pytest.raises(ValueError, match="escapes its storage root"):
        codec.encode(unsafe)


def test_v2_preserved_files_cannot_overwrite_generated_project_files():
    codec = Version2ProjectCodec()
    collision = replace(
        _project(),
        unknown_files=(PreservedProjectFile(
            "project.yaml", "not the manifest", "unknown"
        ),),
    )

    issues = codec.validate(collision)

    assert any("Duplicate project path" in issue.message for issue in issues)
    with pytest.raises(ValueError, match="paths collide"):
        codec.encode(collision)


def test_v2_decoder_reports_unsafe_input_addresses_without_loading_them():
    codec = Version2ProjectCodec()
    project = codec.decode({
        "MANUSKRIPT": "2",
        "project.yaml": "manuskript:\n  format: 2\n",
        "../outside.md": "not part of the project",
    })

    assert project.file("../outside.md") is None
    assert any(
        "escapes its storage root" in issue.message for issue in project.issues
    )
