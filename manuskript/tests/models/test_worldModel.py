from PyQt5.QtCore import QModelIndex

from manuskript.enums import World
from manuskript.models.worldModel import worldModel


def test_add_item_uses_only_the_explicit_parent():
    model = worldModel()
    place = model.addItem("Place")
    city = model.addItem("City", parent=place)

    assert model.rowCount() == 1
    assert place.rowCount() == 1
    assert city.parent() == place
    assert model.name(model.indexFromItem(city)) == "City"


def test_remove_items_normalizes_columns_and_selected_descendants():
    model = worldModel()
    parent = model.addItem("Parent")
    model.addItem("Child", parent=parent)
    sibling = model.addItem("Sibling")

    parent_index = model.indexFromItem(parent)
    child_index = model.index(0, World.name, parent_index)
    sibling_index = model.indexFromItem(sibling)

    removed = model.removeItems([
        parent_index,
        parent_index.sibling(parent_index.row(), World.description),
        child_index,
        sibling_index,
    ])

    assert removed == 2
    assert model.rowCount() == 0


def test_remove_items_rejects_invalid_and_foreign_indexes():
    model = worldModel()
    model.addItem("Kept")
    foreign = worldModel()
    foreign.addItem("Foreign")

    assert model.removeItems([
        QModelIndex(),
        foreign.index(0, World.name),
    ]) == 0
    assert model.rowCount() == 1


def test_populate_data_set_accepts_a_name_instead_of_a_menu_sender():
    model = worldModel()
    data_set_name = next(iter(model.dataSets()))

    added = model.populateDataSet(data_set_name)

    assert added
    assert model.rowCount() == 5
    assert model.populateDataSet("missing") == []
    assert not model.indexByID("missing").isValid()
