from unittest.mock import MagicMock

from manuskript.enums import Character, Plot
from manuskript.ui.project_view_binding import (
    DebugProjectBinding,
    FlatDataProjectBinding,
    OutlineSelectionProjectBinding,
)


def test_flat_data_binding_configures_summary_and_general_fields():
    window = MagicMock()

    FlatDataProjectBinding(window).bind(MagicMock())

    window.txtSummarySituation.setModel.assert_called_once_with(
        window.mdlFlatData
    )
    window.txtSummarySituation.setColumn.assert_called_once_with(0)
    window.txtSummarySituation.setCurrentModelIndex.assert_called_once_with(
        window.mdlFlatData.index.return_value
    )
    window.txtGeneralEmail.setModel.assert_called_once_with(
        window.mdlFlatData
    )
    window.txtGeneralEmail.setColumn.assert_called_once_with(7)
    assert window.mdlFlatData.index.call_count == 19
    window.mdlFlatData.index.assert_any_call(1, 4)
    window.mdlFlatData.index.assert_any_call(0, 7)


def test_outline_selection_binding_registers_project_connections():
    window = MagicMock()
    connect = MagicMock()

    OutlineSelectionProjectBinding(window).bind(connect)

    assert connect.call_count == 7
    connected_slots = [call.args[1] for call in connect.call_args_list]
    assert window.outlineChanged in connected_slots
    assert window.redacOutlineChanged in connected_slots
    assert window.mainEditor.selectionChanged in connected_slots


def test_debug_binding_configures_models_and_named_selection_handlers():
    window = MagicMock()
    connect = MagicMock()
    character_row = 4
    plot_row = 7
    window.tblDebugPersos.selectionModel().currentIndex().row.return_value = (
        character_row
    )
    window.tblDebugPlots.selectionModel().currentIndex().row.return_value = (
        plot_row
    )
    binding = DebugProjectBinding(window)

    binding.bind(connect)
    binding._show_current_character()
    binding._show_current_plot_characters()
    binding._show_current_plot_steps()

    window.tblDebugFlatData.setModel.assert_called_once_with(
        window.mdlFlatData
    )
    window.treeDebugOutline.setModel.assert_called_once_with(
        window.mdlOutline
    )
    assert connect.call_count == 3
    window.mdlCharacter.index.assert_called_once_with(
        character_row,
        Character.name,
    )
    window.mdlPlots.index.assert_any_call(plot_row, Plot.characters)
    window.mdlPlots.index.assert_any_call(plot_row, Plot.steps)
