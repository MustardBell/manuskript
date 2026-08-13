from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, qApp

from manuskript.domain.canonical_project import StructuredMetadataField
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
from manuskript.ui.panels.core.entities import EntityEditorPanel


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


def test_projected_entities_open_read_only_in_the_same_editor():
    catalog, entity = _catalog()
    catalog.replace((), (entity,), writable=False)
    controller = EntityEditorController(QWidget(), catalog, MagicMock())

    assert controller.open(entity.id)
    dialog = controller._dialogs[entity.id]
    assert dialog.titleEdit.isReadOnly()
    assert dialog.bodyEdit.isReadOnly()
    assert not dialog.typeCombo.isEnabled()
    controller.close_all()


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


def test_entity_controller_owns_one_window_modal_child_per_entity():
    catalog, entity = _catalog()
    parent = QWidget()
    update_entity = MagicMock()
    controller = EntityEditorController(parent, catalog, update_entity)

    assert controller.open(entity.id)
    first = controller._dialogs[entity.id]
    assert first.parent() is parent
    assert first.windowModality() == Qt.WindowModal
    assert controller.open(entity.id)
    assert controller._dialogs[entity.id] is first

    first.close()
    qApp.processEvents()
    parent.close()


def test_docked_entity_form_scrolls_instead_of_clipping_its_first_fields():
    catalog, entity = _catalog()
    parent = QWidget()
    panel = EntityEditorPanel(parent)
    panel.resize(320, 220)
    controller = EntityEditorController(
        parent,
        catalog,
        MagicMock(),
        morphology_schemas=first_party_morphology_schemas(),
        host_panel=panel,
    )

    assert controller.open(entity.id)
    panel.show()
    qApp.processEvents()

    assert panel.scrollArea.widget() is panel.editor
    assert panel.editor.titleEdit.text() == "Mara Vale"
    assert panel.editor.morphologyButton.isEnabled()
    assert panel.scrollArea.verticalScrollBar().maximum() > 0
    controller.close_all()
    parent.close()
