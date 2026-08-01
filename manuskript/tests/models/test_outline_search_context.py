from unittest.mock import MagicMock

from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.models.outlineModel import outlineModel
from manuskript.models.outline_search_context import OutlineSearchContext


def make_related_models():
    character_model = MagicMock()
    character = MagicMock()
    character.name.return_value = "Alice"
    character_model.getCharacterByID.return_value = character

    status_model = QStandardItemModel()
    status_model.appendRow(QStandardItem("Draft"))
    status_model.appendRow(QStandardItem("Final"))

    label_model = QStandardItemModel()
    label_model.appendRow(QStandardItem("Idea"))
    label_model.appendRow(QStandardItem("Scene"))
    return character_model, status_model, label_model


def test_outline_search_context_resolves_cross_model_values():
    context = OutlineSearchContext.from_models(*make_related_models())
    model = outlineModel(search_context=context)
    item = outlineItem(title="Opening", _type="md", parent=model.rootItem)
    item.setData(Outline.POV, "7")
    item.setData(Outline.status, "1")
    item.setData(Outline.label, "1")

    assert item.searchData(Outline.POV) == "Alice"
    assert item.searchData(Outline.status) == "Final"
    assert item.searchData(Outline.label) == "Scene"
    assert model.findItemsContaining("alice", [Outline.POV]) == [item.ID()]
    assert model.findItemsContaining("final", [Outline.status]) == [item.ID()]


def test_outline_search_context_handles_missing_related_rows():
    character_model, status_model, label_model = make_related_models()
    character_model.getCharacterByID.return_value = None
    context = OutlineSearchContext.from_models(
        character_model,
        status_model,
        label_model,
    )
    model = outlineModel(search_context=context)
    item = outlineItem(title="Opening", _type="md", parent=model.rootItem)
    item.setData(Outline.POV, "missing")
    item.setData(Outline.status, "99")
    item.setData(Outline.label, "99")

    assert item.searchData(Outline.POV) == ""
    assert item.searchData(Outline.status) == ""
    assert item.searchData(Outline.label) == ""


def test_isolated_outline_model_searches_intrinsic_columns_without_window():
    model = outlineModel()
    item = outlineItem(title="Opening", _type="md", parent=model.rootItem)
    item.setData(Outline.notes, "Remember the key")

    assert model.findItemsContaining("KEY", [Outline.notes]) == [item.ID()]
