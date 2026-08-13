from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, qApp

from manuskript.domain.canonical_project import (
    EntityRecord,
    OutlineDocument,
    StructuredMetadataField,
)
from manuskript.domain.entity_catalog import (
    EntityCatalog,
    first_party_story_entity_schemas,
)
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_schemas
from manuskript.ui.entity_editor import (
    EntityEditorController,
    EntityEditorDialog,
)


def _catalog():
    catalog = EntityCatalog(
        first_party_story_entity_schemas(),
        id_factory=lambda: "entity-mara",
    )
    catalog.replace((), writable=True)
    entity = catalog.create("character", "Mara Vale", ("Mara",))
    return catalog, entity


def test_entity_dialog_exposes_labeled_fields_and_saves_generic_values():
    catalog, entity = _catalog()
    save_entity = MagicMock()
    dialog = EntityEditorDialog(
        entity, catalog.schemas.schemas, save_entity
    )
    dialog.titleEdit.setText("Mara Vane")
    dialog.aliasesEdit.setPlainText("Mara\nMs Vane")
    dialog.bodyEdit.setPlainText("Updated notes.\n")

    dialog.save()

    save_entity.assert_called_once_with(
        "entity-mara",
        title="Mara Vane",
        entity_type="character",
        aliases=("Mara", "Ms Vane"),
        text="Updated notes.\n",
        metadata=(),
    )
    assert dialog.result() == dialog.Accepted
    assert dialog.titleEdit.accessibleName() == "Entity title"
    assert dialog.aliasesEdit.accessibleName() == "Aliases, one per line"
    assert dialog.bodyEdit.accessibleName() == "Entity Markdown document"


def test_entity_dialog_exposes_and_preserves_structured_properties():
    catalog, entity = _catalog()
    entity = catalog.update(
        entity.id,
        metadata=(
            StructuredMetadataField("role", "protagonist"),
            StructuredMetadataField("legacy.steps", [{"name": "Turn"}]),
        ),
    )
    save_entity = MagicMock()
    dialog = EntityEditorDialog(
        entity, catalog.schemas.schemas, save_entity
    )

    assert dialog.propertiesTable.rowCount() == 2
    assert dialog.propertiesTable.item(0, 0).text() == "role"
    dialog.save()

    assert save_entity.call_args.kwargs["metadata"] == entity.metadata


def test_projected_entities_follow_their_per_entity_edit_permission():
    catalog, entity = _catalog()
    catalog.replace(
        (), (entity,), writable=False,
        editable_projected_ids=(entity.id,),
    )
    parent = QMainWindow()
    controller = EntityEditorController(parent, catalog, MagicMock())

    assert controller.open(entity.id)
    dialog = controller.dialog_for(entity.id)
    assert not dialog.titleEdit.isReadOnly()
    assert not dialog.bodyEdit.isReadOnly()
    # A legacy character stays a character; only Format 2 entities can move
    # freely between schema-defined types.
    assert not dialog.typeCombo.isEnabled()
    controller.close_all()
    parent.close()


def test_unwritable_projected_entity_remains_read_only():
    catalog, entity = _catalog()
    catalog.replace((), (entity,), writable=False)
    parent = QMainWindow()
    controller = EntityEditorController(parent, catalog, MagicMock())

    assert controller.open(entity.id)
    dialog = controller.dialog_for(entity.id)
    assert dialog.titleEdit.isReadOnly()
    assert dialog.bodyEdit.isReadOnly()
    controller.close_all()
    parent.close()


def test_entity_dialog_accepts_an_extension_defined_type():
    catalog, entity = _catalog()
    save_entity = MagicMock()
    dialog = EntityEditorDialog(
        entity, catalog.schemas.schemas, save_entity
    )
    dialog.typeCombo.setEditText("creature")

    dialog.save()

    assert save_entity.call_args.kwargs["entity_type"] == "creature"


def test_entity_dialog_saves_author_reviewed_morphology_as_entity_metadata():
    catalog, entity = _catalog()
    save_entity = MagicMock()
    schemas = first_party_morphology_schemas()
    dialog = EntityEditorDialog(
        entity,
        catalog.schemas.schemas,
        save_entity,
        morphology_schemas=schemas,
        morphology_enabled=True,
    )
    dialog._morphologyProfile = MorphologyProfile(
        "uk",
        "uk.personal-names",
        (MorphologyComponent(
            "given-name", "Мара", (("gender", "feminine"),)
        ),),
    )
    dialog._morphologyChanged = True

    dialog.save()

    metadata = save_entity.call_args.kwargs["metadata"]
    assert metadata[0].name == "morphology"
    assert metadata[0].value["language"] == "uk"
    assert metadata[0].value["schema"] == "uk.personal-names"
    assert dialog.morphologyButton.isEnabled()


def test_legacy_entity_treats_morphology_named_metadata_as_opaque_data():
    catalog, entity = _catalog()
    entity = catalog.update(
        entity.id,
        metadata=(StructuredMetadataField(
            "morphology",
            {"language": "uk", "schema": "uk.personal-names"},
        ),),
    )
    dialog = EntityEditorDialog(
        entity,
        catalog.schemas.schemas,
        MagicMock(),
        morphology_schemas=first_party_morphology_schemas(),
        morphology_enabled=False,
        read_only=True,
    )

    assert not dialog.morphologyButton.isEnabled()
    assert dialog.propertiesTable.rowCount() == 1
    assert dialog.propertiesTable.item(0, 0).text() == "morphology"


def test_legacy_transport_metadata_is_hidden_but_preserved_on_save():
    entity = EntityRecord(
        OutlineDocument(
            "legacy:character:17", "Olena", "entity", "Notes",
            source_path="characters/17-Olena.txt",
        ),
        "character",
        metadata=(
            StructuredMetadataField("legacy.id", "17"),
            StructuredMetadataField("legacy.color", "#336699"),
            StructuredMetadataField("Language", "uk"),
        ),
    )
    save_entity = MagicMock()
    dialog = EntityEditorDialog(
        entity,
        first_party_story_entity_schemas().schemas,
        save_entity,
        morphology_schemas=first_party_morphology_schemas(),
        morphology_enabled=False,
    )

    assert dialog.morphologyButton.isHidden()
    assert dialog.morphologySummary.isHidden()
    assert dialog.propertiesTable.rowCount() == 1
    assert dialog.propertiesTable.item(0, 0).text() == "Language"
    dialog.save()

    metadata = save_entity.call_args.kwargs["metadata"]
    assert StructuredMetadataField("legacy.id", "17") in metadata
    assert StructuredMetadataField("legacy.color", "#336699") in metadata


def test_entity_controller_owns_floating_dockable_detail_windows():
    catalog, entity = _catalog()
    parent = QMainWindow()
    update_entity = MagicMock()
    controller = EntityEditorController(parent, catalog, update_entity)

    assert controller.open(entity.id)
    first = controller.dialog_for(entity.id)
    dock = controller._docks[0]
    assert first.parent() is dock
    assert first.windowModality() == Qt.NonModal
    assert dock.isFloating()
    assert dock.allowedAreas() == Qt.AllDockWidgetAreas
    assert controller.open(entity.id)
    assert controller.dialog_for(entity.id) is first
    assert len(controller._docks) == 1

    dock.close()
    qApp.processEvents()
    parent.close()


def test_primary_detail_retargets_and_alt_opening_keeps_an_extra_window():
    catalog, entity = _catalog()
    catalog._id_factory = lambda: "entity-olena"
    second = catalog.create("character", "Olena")
    parent = QMainWindow()
    controller = EntityEditorController(
        parent,
        catalog,
        MagicMock(),
        morphology_schemas=first_party_morphology_schemas(),
        morphology_enabled=True,
    )

    assert controller.open(entity.id)
    first_dock = controller._docks[0]
    assert controller.retarget(second.id)
    assert controller.dialog_for(entity.id) is None
    assert controller.dialog_for(second.id) is not None
    assert first_dock not in controller._docks

    assert controller.retarget(entity.id, new_window=True)
    assert controller.dialog_for(entity.id) is not None
    assert controller.dialog_for(second.id) is not None
    assert len(controller.pending_editors()) == 2
    controller.close_all()
    parent.close()
