from unittest.mock import MagicMock

from PyQt5.QtCore import QModelIndex

from manuskript.controllers.world_controller import WorldController
from manuskript.enums import World
from manuskript.models.worldModel import worldModel
from manuskript.ui.views.world_panel import WorldPanelView


def make_controller():
    """The panel it drives and the model it edits, named.

    A real world model, because these tests are about coordinating one
    with the tree beside it; everything else is a double.
    """
    model = worldModel()
    item = model.addItem("Place")
    index = model.indexFromItem(item)
    models = MagicMock()
    models.world = model
    panel = WorldPanelView(
        tree=MagicMock(),
        tabs=MagicMock(),
        data_set_button=MagicMock(),
        add_item_button=MagicMock(),
        remove_item_button=MagicMock(),
        fields=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
    )
    panel.tree.selectedIndexes.return_value = [index]
    panel.tree.currentIndex.return_value = index
    navigation = MagicMock()
    dialogs = MagicMock()
    dialogs.translate.side_effect = lambda text: text
    controller = WorldController(models, panel, navigation, dialogs)
    return controller, panel, model, item, index, navigation


def test_selection_binds_world_fields_and_records_history():
    controller, panel, model, _item, index, navigation = (
        make_controller()
    )

    controller.handle_selection_changed()

    panel.tabs.setEnabled.assert_called_once_with(True)
    for widget in panel.fields:
        widget.setCurrentModelIndex.assert_called_once_with(index)
    # One statement rather than a push and a flag set across a boundary.
    navigation.record.assert_called_once_with(
        ("world", model.ID(index)),
        selection_empty=False,
    )


def test_record_empty_selection_sets_history_state_in_the_right_direction():
    controller, panel, _model, _item, _index, navigation = (
        make_controller()
    )
    panel.tree.selectedIndexes.return_value = []
    panel.tree.currentIndex.return_value = QModelIndex()

    controller.record_current_selection()

    navigation.record.assert_called_once_with(
        ("world", None),
        selection_empty=True,
    )


def test_add_item_coordinates_parent_expansion_and_new_selection():
    controller, panel, model, parent, parent_index, _nav = (
        make_controller()
    )

    item = controller.add_item(title="City")

    assert item.parent() == parent
    assert model.name(model.indexFromItem(item)) == "City"
    panel.tree.setExpanded.assert_called_once_with(
        parent_index,
        True,
    )
    panel.tree.setCurrentIndex.assert_called_once_with(
        model.indexFromItem(item)
    )


def test_remove_selected_items_passes_explicit_tree_indexes():
    controller, panel, model, _item, index, _nav = make_controller()
    duplicate_column = index.sibling(index.row(), World.description)
    panel.tree.selectedIndexes.return_value = [
        index,
        duplicate_column,
    ]

    assert controller.remove_selected_items() == 1
    assert model.rowCount() == 0


def test_select_by_id_handles_present_and_missing_items():
    controller, panel, model, _item, index, _nav = make_controller()
    world_id = model.ID(index)

    assert controller.select_by_id(world_id)
    panel.tree.setCurrentIndex.assert_called_once_with(index)
    assert not controller.select_by_id("missing")
