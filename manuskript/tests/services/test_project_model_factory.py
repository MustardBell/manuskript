from PyQt5.QtCore import QObject
from PyQt5.QtGui import QStandardItem

from manuskript.enums import Outline
from manuskript.models import outlineItem
from manuskript.models.outline_settings import DefaultOutlineSettings
from manuskript.services.project_model_factory import ProjectModelFactory


def test_project_model_factory_builds_connected_model_graph():
    parent = QObject()
    settings = DefaultOutlineSettings()

    models = ProjectModelFactory().create(parent, settings)

    assert models.outline.settings is settings

    character = models.characters.addCharacter(name="Alice")
    assert models.plots._character_lookup(character.ID()) is character

    models.statuses.appendRow(QStandardItem("Draft"))
    models.labels.appendRow(QStandardItem("Scene"))
    item = outlineItem(title="Opening", settings=settings)
    item.setData(Outline.POV, character.ID())
    item.setData(Outline.status, "0")
    item.setData(Outline.label, "0")

    assert (
        models.outline.search_context.value_for(item, Outline.POV)
        == "Alice"
    )
    assert (
        models.outline.search_context.value_for(item, Outline.status)
        == "Draft"
    )
    assert (
        models.outline.search_context.value_for(item, Outline.label)
        == "Scene"
    )


def test_project_models_install_legacy_window_attributes():
    models = ProjectModelFactory().create(
        QObject(),
        DefaultOutlineSettings(),
    )

    class Window:
        pass

    window = Window()
    models.install_on(window)

    assert window.mdlFlatData is models.flat_data
    assert window.mdlCharacter is models.characters
    assert window.mdlLabels is models.labels
    assert window.mdlStatus is models.statuses
    assert window.mdlPlots is models.plots
    assert window.mdlOutline is models.outline
    assert window.mdlWorld is models.world
