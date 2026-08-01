from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItem

from manuskript.enums import Outline
from manuskript.functions import iconFromColor
from manuskript.models import outlineItem


@dataclass(frozen=True)
class ProjectTemplateModels:
    flat_data: object
    labels: object
    statuses: object
    outline: object


class ProjectTemplateInitializer:
    """Populate newly-created project models from a welcome-screen template."""

    def __init__(
            self, settings, load_empty_project: Callable,
            models: Callable[[], ProjectTemplateModels]):
        self.settings = settings
        self.load_empty_project = load_empty_project
        self.models = models

    def initialize(self, template, non_fiction, labels, statuses):
        self.settings.reset_to_defaults()
        self.load_empty_project()
        models = self.models()

        if non_fiction:
            self.settings.viewMode = "simple"

        models.flat_data.setRowCount(2)
        models.flat_data.setColumnCount(8)

        for color, text in labels:
            models.labels.appendRow(
                QStandardItem(iconFromColor(color), text)
            )

        for text in statuses:
            models.statuses.appendRow(QStandardItem(text))

        if template and template[1]:
            self._add_elements(models.outline.rootItem, template[1])

    def _add_elements(self, parent, rows):
        next_row_is_word_count = (
            len(rows) == 2 and rows[1][1] is None
        )
        if next_row_is_word_count or len(rows) == 1:
            for number in range(1, rows[0][0] + 1):
                item = outlineItem(
                    title="{} {}".format(rows[0][1], number),
                    _type="md",
                    parent=parent,
                )
                if len(rows) == 2:
                    item.setData(Outline.setGoal, rows[1][0])
            return

        for number in range(1, rows[0][0] + 1):
            item = outlineItem(
                title="{} {}".format(rows[0][1], number),
                _type="folder",
                parent=parent,
            )
            self._add_elements(item, rows[1:])
