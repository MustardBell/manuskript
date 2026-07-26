from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from manuskript.enums import Outline
from manuskript.functions import (
    colorFromProgress,
    iconColor,
    mixColors,
    toInt,
)
from manuskript.ui import style


class OutlineColorResolver:
    """Resolve outline colors from the models assigned to the current view."""

    def __init__(self, character_model=None, label_model=None):
        self.character_model = character_model
        self.label_model = label_model

    def colors_for(self, item):
        colors = {
            "POV": QColor(Qt.transparent),
            "Label": QColor(Qt.transparent),
        }

        pov = item.data(Outline.POV)
        if pov != "" and self.character_model is not None:
            for row in range(self.character_model.rowCount()):
                if self.character_model.ID(row) == pov:
                    colors["POV"] = iconColor(
                        self.character_model.icon(row)
                    )
                    break

        label = item.data(Outline.label)
        if label != "" and self.label_model is not None:
            label_item = self.label_model.item(toInt(label))
            if label_item is not None:
                colors["Label"] = iconColor(label_item.icon())

        progress = (
            item.data(Outline.goalPercentage)
            if item.data(Outline.setGoal)
            else None
        )
        colors["Progress"] = colorFromProgress(progress)

        if item.compile() in [0, "0"]:
            colors["Compile"] = mixColors(
                QColor(style.text),
                QColor(style.window),
            )
        else:
            colors["Compile"] = QColor(Qt.transparent)

        return colors
