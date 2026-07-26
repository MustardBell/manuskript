from unittest.mock import MagicMock

from PyQt5.QtCore import QModelIndex

from manuskript.controllers.world_controller import WorldController
from manuskript.enums import World
from manuskript.models.worldModel import worldModel


def make_controller():
    window = MagicMock()
    window.tr.side_effect = lambda text: text
    model = worldModel()
    item = model.addItem("Place")
    index = model.indexFromItem(item)
    window.mdlWorld = model
    window.treeWorld.selectedIndexes.return_value = [index]
    window.treeWorld.currentIndex.return_value = index
    return WorldController(window), window, model, item, index


def test_selection_binds_world_fields_and_records_history():
    controller, window, model, _item, index = make_controller()

    controller.handle_selection_changed()

    window.tabWorld.setEnabled.assert_called_once_with(True)
    for widget in [
        window.txtWorldName,
        window.txtWorldDescription,
        window.txtWorldPassion,
        window.txtWorldConflict,
    ]:
        widget.setCurrentModelIndex.assert_called_once_with(index)
    window.pushHistory.assert_called_once_with(
        ("world", model.ID(index))
    )
    assert window._previousSelectionEmpty is False


def test_record_empty_selection_sets_history_state_in_the_right_direction():
    controller, window, _model, _item, _index = make_controller()
    window.treeWorld.selectedIndexes.return_value = []
    window.treeWorld.currentIndex.return_value = QModelIndex()

    controller.record_current_selection()

    window.pushHistory.assert_called_once_with(("world", None))
    assert window._previousSelectionEmpty is True


def test_add_item_coordinates_parent_expansion_and_new_selection():
    controller, window, model, parent, parent_index = make_controller()

    item = controller.add_item(title="City")

    assert item.parent() == parent
    assert model.name(model.indexFromItem(item)) == "City"
    window.treeWorld.setExpanded.assert_called_once_with(
        parent_index,
        True,
    )
    window.treeWorld.setCurrentIndex.assert_called_once_with(
        model.indexFromItem(item)
    )


def test_remove_selected_items_passes_explicit_tree_indexes():
    controller, window, model, _item, index = make_controller()
    duplicate_column = index.sibling(index.row(), World.description)
    window.treeWorld.selectedIndexes.return_value = [
        index,
        duplicate_column,
    ]

    assert controller.remove_selected_items() == 1
    assert model.rowCount() == 0


def test_select_by_id_handles_present_and_missing_items():
    controller, window, model, _item, index = make_controller()
    world_id = model.ID(index)

    assert controller.select_by_id(world_id)
    window.treeWorld.setCurrentIndex.assert_called_once_with(index)
    assert not controller.select_by_id("missing")
