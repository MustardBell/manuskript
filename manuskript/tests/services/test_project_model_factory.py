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


def test_the_models_say_which_of_them_mean_unsaved_changes():
    """A window used to answer this, so the project could only learn what
    makes it dirty by asking something that displays it.
    """
    # The parent is held for the length of the test: Qt deletes children
    # with their parent, and a collected local would take the models.
    parent = QObject()
    models = ProjectModelFactory().create(
        parent,
        DefaultOutlineSettings(),
    )

    sources = models.change_sources

    assert set(sources) == {
        models.flat_data,
        models.outline,
        models.characters,
        models.plots,
        models.world,
        models.statuses,
        models.labels,
    }
    # Not an item model, so there is no change of its to connect to.
    assert models.plugin_data not in sources
    for model in sources:
        assert hasattr(model, "dataChanged")


def test_project_models_cannot_be_installed_on_a_window():
    """The graph belongs to the runtime and is read there explicitly.

    Installing aliases on a window made the view look like an owner and
    allowed any collaborator holding that window to use it as a service
    locator for project state.
    """
    models = ProjectModelFactory().create(
        QObject(),
        DefaultOutlineSettings(),
    )

    assert not hasattr(models, "install_on")
