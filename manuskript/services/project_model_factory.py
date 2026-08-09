from dataclasses import dataclass

from PyQt5.QtGui import QStandardItemModel

from manuskript.domain.plugin_data import ProjectPluginData
from manuskript.models import outlineModel
from manuskript.models.characterModel import characterModel
from manuskript.models.outline_search_context import OutlineSearchContext
from manuskript.models.plotModel import plotModel
from manuskript.models.worldModel import worldModel


@dataclass(frozen=True)
class ProjectModels:
    flat_data: object
    characters: object
    labels: object
    statuses: object
    plots: object
    outline: object
    world: object
    plugin_data: ProjectPluginData

    @property
    def change_sources(self):
        """The models whose edits mean the project has unsaved changes.

        Asked of the models themselves. Which of them signal a change is
        a fact about the model graph, and it used to be answered by a
        window -- so the project could only learn what makes it dirty
        from something that merely displays it.

        ``plugin_data`` is absent deliberately: it is not an item model
        and has no ``dataChanged`` to connect.
        """
        return (
            self.flat_data,
            self.outline,
            self.characters,
            self.plots,
            self.world,
            self.statuses,
            self.labels,
        )

class ProjectModelFactory:
    """Build a complete, internally connected project model graph."""

    def create(self, parent, settings):
        flat_data = QStandardItemModel(parent)
        characters = characterModel(parent)
        labels = QStandardItemModel(parent)
        statuses = QStandardItemModel(parent)
        plots = plotModel(
            parent,
            character_lookup=characters.getCharacterByID,
        )
        outline = outlineModel(
            parent,
            search_context=OutlineSearchContext.from_models(
                characters,
                statuses,
                labels,
            ),
            settings=settings,
        )
        world = worldModel(parent)
        plugin_data = ProjectPluginData()
        return ProjectModels(
            flat_data=flat_data,
            characters=characters,
            labels=labels,
            statuses=statuses,
            plots=plots,
            outline=outline,
            world=world,
            plugin_data=plugin_data,
        )
