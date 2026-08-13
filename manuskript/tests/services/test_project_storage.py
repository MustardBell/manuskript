from unittest.mock import MagicMock
from pathlib import Path

from PyQt5.QtCore import QObject

from manuskript.domain.persistence import (
    ProjectSaveResult,
)
from manuskript.domain.canonical_project import (
    CanonicalProject,
    OutlineDocument,
    StructuredMetadataField,
)
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.domain.assertion_dsl import encode_assertion_block
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTerm,
    StoryReference,
    TemporalInterval,
    TemporalPoint,
)
from manuskript.domain.temporal_story import TemporalFactStatus
from manuskript.domain.revision_workflow import RevisionPassState
from manuskript.domain.story_query import (
    AssertionsWhere,
    QueryResult,
    QueryScope,
)
from manuskript.domain.rule_dsl import (
    CustomRuleDefinition,
    CustomRuleKind,
    encode_rule_block,
)
from manuskript.load_save.format_detection import DetectedProjectFormat
from manuskript.load_save.project_codec import EncodedProject
from manuskript.load_save.project_files import ProjectFileReadResult
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.legacy_archive import Version0ProjectArchive
from manuskript.load_save import version_0
from manuskript.load_save.version_1_codec import Version1ProjectCodec
from manuskript.load_save.version_2_codec import Version2ProjectCodec
from manuskript.services.project_storage import ProjectStorage
from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import ProjectPersistenceContext
from manuskript.settingsManager import SettingsManager
from manuskript.enums import Character, Outline


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
        "story.msk", zipped=False, files=(), moves=(), cache=cache,
        marker_version=1,
    )


def test_capture_current_projects_live_models_without_writing_or_adopting():
    context = MagicMock()
    current = CanonicalProject(format_version=2)
    live = CanonicalProject(
        format_version=2,
        outline=(OutlineDocument("scene", "Live", "scene", "changed"),),
    )
    adapter = MagicMock()
    adapter.capture.return_value = live
    storage = ProjectStorage(application_model_adapter=adapter)
    storage._canonical_project = current
    storage.entity_catalog.replace((), writable=True)

    captured = storage.capture_current(context)

    assert captured == live
    assert storage.canonical_project is current
    adapter.capture.assert_called_once_with(context, current)


def test_storage_clears_persistence_cache():
    cache = {"outline/scene.md": "text"}
    storage = ProjectStorage(file_cache=cache)
    storage._canonical_project = CanonicalProject(format_version=1)

    storage.clear_cache()

    assert cache == {}
    assert storage.canonical_project is None


def test_legacy_project_text_is_not_indexed_as_format_2_story_syntax():
    assertion = Assertion(
        "looks-structured",
        StoryReference("entity", "mara"),
        "knows",
        AssertionTerm.scalar("something"),
    )
    source = (
        "Literal [[Characters/Mara|Mara]].\n\n"
        + encode_assertion_block(assertion)
    )
    project = CanonicalProject(
        format_version=1,
        outline=(OutlineDocument(
            "scene", "Scene", "scene", source, "outline/scene.md"
        ),),
    )
    storage = ProjectStorage()

    storage._adopt_canonical_project(project)

    assert not storage.reference_index.enabled
    assert storage.reference_index.references == ()
    assert storage.assertion_store.assertions == ()
    assert storage.rule_store.rules == ()


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


def test_format_one_entities_edit_and_create_through_the_common_surface(
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
        str(project_file), models, settings
    )
    storage = ProjectStorage()
    assert storage.load(context).succeeded
    olena = storage.entity_catalog.find("legacy:character:17")
    metadata = tuple(
        StructuredMetadataField(
            field.name,
            "1" if field.name == "Importance" else field.value,
        )
        for field in olena.metadata
    )

    storage.update_entity(
        olena.id,
        title="Олена Вовк",
        aliases=("Лена", "Оленка"),
        text="Edited through the shared entity form.",
        metadata=metadata,
    )
    created = storage.create_entity("character", "Mara Vale", ("Mara",))
    assert created.id.startswith("legacy:character:")
    assert storage.save(context).succeeded

    persisted = Version1ProjectFiles().read(
        str(project_file), zipped=False
    ).files
    reopened = Version1ProjectCodec().decode(persisted)
    updated = next(item for item in reopened.characters if item.id == "17")
    new_character = next(
        item for item in reopened.characters if item.name == "Mara Vale"
    )

    assert updated.name == "Олена Вовк"
    assert updated.value("Importance") == "1"
    assert updated.value("Notes") == "Edited through the shared entity form."
    assert updated.color == "#336699"
    assert any(
        field.name == "Language" and field.value == "uk"
        for field in updated.custom_fields
    )
    assert any(
        field.name in ("Alias", "Aliases") and "Лена" in field.value
        for field in updated.custom_fields
    )
    assert any(
        field.name == "Aliases" and field.value == "Mara"
        for field in new_character.custom_fields
    )
    assert reopened.file("unrecognized.future").content == (
        "opaque future data\n"
    )


def test_format_zero_characters_use_the_same_writable_surface_and_round_trip(
    tmp_path, test_application,
):
    project_file = tmp_path / "legacy.msk"
    first_settings = SettingsManager()
    first_parent = QObject()
    first_models = ProjectModelFactory().create(first_parent, first_settings)
    first_context = ProjectPersistenceContext(
        str(project_file), first_models, first_settings
    )
    character = first_models.characters.addCharacter(name="Legacy Mara")
    first_models.characters.setData(
        character.index(Character.motivation), "Find the archive."
    )
    assert version_0.saveProject(
        first_context, archive=Version0ProjectArchive()
    ).succeeded

    second_settings = SettingsManager()
    second_parent = QObject()
    second_models = ProjectModelFactory().create(second_parent, second_settings)
    second_context = ProjectPersistenceContext(
        str(project_file), second_models, second_settings
    )
    storage = ProjectStorage()
    assert storage.load(second_context).succeeded
    projected = next(
        item for item in storage.entity_catalog.entities
        if item.type == "character"
    )
    assert storage.entity_catalog.can_edit(projected.id)
    assert not storage.entity_catalog.writable

    storage.update_entity(
        projected.id,
        title="Legacy Mara Vane",
        text="Persisted notes.",
    )
    assert storage.save(second_context).succeeded

    third_settings = SettingsManager()
    third_parent = QObject()
    third_models = ProjectModelFactory().create(third_parent, third_settings)
    third_context = ProjectPersistenceContext(
        str(project_file), third_models, third_settings
    )
    reopened = ProjectStorage()
    assert reopened.load(third_context).succeeded
    entity = next(
        item for item in reopened.entity_catalog.entities
        if item.type == "character"
    )
    assert entity.title == "Legacy Mara Vane"
    assert entity.document.text == "Persisted notes."


def test_real_v2_storage_stays_v2_and_keeps_opaque_document_identity(tmp_path):
    codec = Version2ProjectCodec()
    document_id = "018f1f42-c546-7d20-bf25-b8d70433c123"
    source_project = CanonicalProject(
        format_version=2,
        outline=(
            OutlineDocument(
                id=document_id,
                title="Opening",
                kind="scene",
                text="Original [[Opening]].\n",
            ),
            OutlineDocument(
                id="untouched",
                title="Untouched",
                kind="notes",
                text="Do not normalize this document.\n",
                structured_metadata=(
                    StructuredMetadataField(
                        "external-tool", {"keep": True}
                    ),
                ),
            ),
            OutlineDocument(
                id="legacy-mmd",
                title="Legacy",
                kind="md",
                text="Legacy body.\n",
            ),
        ),
        settings_source="{}",
        structured_metadata=(
            StructuredMetadataField("external-project", {"keep": True}),
        ),
    )
    encoded = codec.encode(source_project)
    encoded_files = dict(encoded.files)
    untouched_path = next(
        document.source_path
        for document in codec.decode(encoded_files).documents()
        if document.id == "untouched"
    )
    untouched_source = encoded_files[untouched_path]
    legacy_path = next(
        document.source_path
        for document in codec.decode(encoded_files).documents()
        if document.id == "legacy-mmd"
    )
    legacy_source = (
        "title:          Legacy\n"
        "ID:             legacy-mmd\n"
        "type:           md\n\n\n"
        "Legacy body.\n"
    )
    encoded_files[legacy_path] = legacy_source
    project_file = tmp_path / "native.msk"
    access = Version1ProjectFiles()
    assert access.write(
        str(project_file), zipped=False, files=tuple(encoded_files.items()),
        moves=(), cache={}, marker_version=2,
    ).succeeded

    settings = SettingsManager()
    parent = QObject()
    models = ProjectModelFactory().create(parent, settings)
    context = ProjectPersistenceContext(
        str(project_file), models, settings
    )
    storage = ProjectStorage()

    loaded = storage.load(context)
    item = models.outline.getItemByID(document_id)
    assert len(storage.reference_index.backlinks(document_id)) == 1
    item.setData(Outline.text, "Changed through the UI adapter.\n")
    storage.update_document_references(item)
    assert not storage.reference_index.backlinks(document_id)
    created_entity = storage.create_entity(
        "character", "Mara Vale", ("Mara",)
    )
    assert storage.reference_index.resolve("Characters/Mara Vale")[1].id == (
        created_entity.id
    )
    created_entity = storage.update_entity(
        created_entity.id,
        title="Mara Vane",
        aliases=("M. Vane",),
        text="Entity notes.\n",
    )
    assert storage.reference_index.resolve("M. Vane")[1].id == (
        created_entity.id
    )
    morphology = MorphologyProfile(
        "uk",
        "uk.personal-names",
        (MorphologyComponent(
            "given-name", "Олена", (("gender", "feminine"),)
        ),),
    )
    inflected_entity = storage.create_entity("character", "Олена")
    inflected_entity = storage.update_entity(
        inflected_entity.id,
        metadata=morphology.apply_to(inflected_entity.metadata),
    )
    assert storage.entity_catalog.exact_matches("Олени")[0].id == (
        inflected_entity.id
    )
    assert storage.reference_index.complete("Олені")[0].document_id == (
        inflected_entity.id
    )
    assertion = Assertion(
        "mara-knows-olena",
        StoryReference("entity", created_entity.id),
        "knows",
        AssertionTerm.referencing("entity", inflected_entity.id),
        validity=TemporalInterval(
            TemporalPoint.narrative("document", document_id)
        ),
    )
    item.setData(
        Outline.text,
        item.text()
        + "\n"
        + encode_assertion_block(assertion)
        + encode_rule_block(CustomRuleDefinition(
            "custom-knows",
            "Knowledge remains unique",
            CustomRuleKind.EXCLUSIVE_OBJECT,
            predicate="knows",
        )),
    )
    storage.update_document_references(item)
    assert storage.assertion_store.assertions[0].id == assertion.id
    assert storage.rule_store.rules[0].id == "custom-knows"
    assert storage.temporal_story.evaluate(
        storage.assertion_store.assertions[0],
        TemporalPoint.narrative("document", document_id),
    ).status is TemporalFactStatus.ACTIVE
    assert storage.story_query.execute(AssertionsWhere(predicate="knows")) == (
        QueryResult(QueryScope.ASSERTION, assertion.id),
    )
    storage.update_revision_pass(
        document_id, "continuity", RevisionPassState.IN_PROGRESS
    )
    saved = storage.save(context)
    persisted = access.read(str(project_file), zipped=False).files
    reopened = codec.decode(persisted)

    assert loaded.succeeded
    assert saved.succeeded
    assert project_file.read_text(encoding="utf-8") == "2"
    assert storage.canonical_project.format_version == 2
    assert tuple(reopened.documents())[0].id == document_id
    assert tuple(reopened.documents())[0].kind == "scene"
    assert tuple(reopened.documents())[0].text.startswith(
        "Changed through the UI adapter.\n"
    )
    workflow_metadata = {
        item.name: item.value
        for item in tuple(reopened.documents())[0].structured_metadata
    }
    assert workflow_metadata[
        "manuskript.revision_workflow"
    ]["passes"]["continuity"] == "in-progress"
    assert persisted[untouched_path] == untouched_source
    assert persisted[legacy_path] == legacy_source
    assert reopened.structured_metadata == source_project.structured_metadata
    assert tuple(reopened.documents())[1].structured_metadata == (
        StructuredMetadataField("external-tool", {"keep": True}),
    )
    reopened_created = next(
        entity for entity in reopened.entities
        if entity.id == created_entity.id
    )
    assert reopened_created.title == "Mara Vane"
    assert reopened_created.aliases == ("M. Vane",)
    assert reopened_created.document.text == "Entity notes.\n"
    reopened_inflected = next(
        entity for entity in reopened.entities
        if entity.id == inflected_entity.id
    )
    assert MorphologyProfile.from_entity(reopened_inflected) == morphology
    assert "mara-knows-olena" in tuple(reopened.documents())[0].text

    copy_file = tmp_path / "native-copy.msk"
    copy_context = ProjectPersistenceContext(
        str(copy_file), models, settings
    )
    assert storage.save(copy_context).succeeded
    assert copy_file.read_text(encoding="utf-8") == "2"
