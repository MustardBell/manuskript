from unittest.mock import MagicMock

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QStandardItem, QStandardItemModel

from manuskript.enums import Outline
from manuskript.functions import iconFromColor
from manuskript.models import outlineItem
from manuskript.ui.views.outline_colors import OutlineColorResolver


def test_outline_colors_are_resolved_from_assigned_models():
    characters = MagicMock()
    characters.rowCount.return_value = 1
    characters.ID.return_value = "7"
    characters.icon.return_value = iconFromColor(Qt.red)

    labels = QStandardItemModel()
    label_icon = QStandardItem()
    label_icon.setIcon(iconFromColor(Qt.blue))
    labels.appendRow(label_icon)

    item = outlineItem(title="Scene")
    item.setData(Outline.POV, "7")
    item.setData(Outline.label, "0")
    resolver = OutlineColorResolver(characters, labels)

    colors = resolver.colors_for(item)

    assert colors["POV"].name() == QColor(Qt.red).name()
    assert colors["Label"].name() == QColor(Qt.blue).name()
    assert colors["Compile"].alpha() == 0


def test_outline_colors_tolerate_cleared_project_models():
    item = outlineItem(title="Scene")
    item.setData(Outline.POV, "42")
    item.setData(Outline.label, "3")

    colors = OutlineColorResolver().colors_for(item)

    assert colors["POV"].alpha() == 0
    assert colors["Label"].alpha() == 0
