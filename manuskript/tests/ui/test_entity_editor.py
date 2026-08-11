from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, qApp

from manuskript.domain.entity_catalog import (
    EntityCatalog,
    first_party_story_entity_schemas,
)
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_providers
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
    )
    assert dialog.result() == dialog.Accepted
    assert dialog.titleEdit.accessibleName() == "Entity title"
    assert dialog.aliasesEdit.accessibleName() == "Aliases, one per line"
    assert dialog.bodyEdit.accessibleName() == "Entity Markdown document"


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
    providers = first_party_morphology_providers()
    dialog = EntityEditorDialog(
        entity,
        catalog.schemas.schemas,
        save_entity,
        morphology_providers=providers,
    )
    dialog._morphologyProfile = MorphologyProfile(
        "uk.personal-names",
        (MorphologyComponent(
            "given-name", "Мара", (("gender", "feminine"),)
        ),),
    )
    dialog._morphologyChanged = True

    dialog.save()

    metadata = save_entity.call_args.kwargs["metadata"]
    assert metadata[0].name == "morphology"
    assert metadata[0].value["provider"] == "uk.personal-names"
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
