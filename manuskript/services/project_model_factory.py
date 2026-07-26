from dataclasses import dataclass

from PyQt5.QtGui import QStandardItemModel

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

    def install_on(self, window):
        """Expose the model graph through the legacy window attributes."""
        window.mdlFlatData = self.flat_data
        window.mdlCharacter = self.characters
        window.mdlLabels = self.labels
        window.mdlStatus = self.statuses
        window.mdlPlots = self.plots
        window.mdlOutline = self.outline
        window.mdlWorld = self.world


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
        return ProjectModels(
            flat_data=flat_data,
            characters=characters,
            labels=labels,
            statuses=statuses,
            plots=plots,
            outline=outline,
            world=world,
        )
