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
from manuskript.load_save.version_1_codec import Version1ProjectCodec
from manuskript.load_save.version_2_codec import Version2ProjectCodec
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
        "story.msk", zipped=False, files=(), moves=(), cache=cache,
        marker_version=1,
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
    assert persisted[untouched_path] == untouched_source
    assert persisted[legacy_path] == legacy_source
    assert reopened.structured_metadata == source_project.structured_metadata
    assert tuple(reopened.documents())[1].structured_metadata == (
        StructuredMetadataField("external-tool", {"keep": True}),
    )
    assert reopened.entities[0].id == created_entity.id
    assert reopened.entities[0].title == "Mara Vane"
    assert reopened.entities[0].aliases == ("M. Vane",)
    assert reopened.entities[0].document.text == "Entity notes.\n"
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
