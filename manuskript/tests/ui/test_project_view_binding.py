from unittest.mock import MagicMock

from manuskript.enums import Character, Plot
from manuskript.ui.project_view_binding import (
    DebugProjectBinding,
    FlatDataProjectBinding,
    OutlineSelectionProjectBinding,
)
from manuskript.ui.project_binding_views import ProjectBindingViews


def test_flat_data_binding_configures_general_fields_but_not_legacy_summary():
    window = MagicMock()
    runtime = MagicMock()
    views = ProjectBindingViews.for_window(window)

    FlatDataProjectBinding(views.flat_data, runtime).bind(MagicMock())

    window.txtSummarySituation.setModel.assert_not_called()
    window.txtGeneralEmail.setModel.assert_called_once_with(
        runtime.models.flat_data
    )
    window.txtGeneralEmail.setColumn.assert_called_once_with(7)
    assert runtime.models.flat_data.index.call_count == 8
    runtime.models.flat_data.index.assert_any_call(0, 7)


def test_outline_selection_binding_registers_project_connections():
    window = MagicMock()
    runtime = MagicMock()
    connect = MagicMock()
    views = ProjectBindingViews.for_window(window)

    OutlineSelectionProjectBinding(views.outline_selection).bind(connect)

    assert connect.call_count == 7
    connected_slots = [call.args[1] for call in connect.call_args_list]
    assert (
        window.workspaceSelection.outline_selection_changed
        in connected_slots
    )
    assert (
        window.workspaceSelection.project_selection_changed
        in connected_slots
    )
    assert window.mainEditor.selectionChanged in connected_slots


def test_debug_binding_configures_models_and_named_selection_handlers():
    window = MagicMock()
    runtime = MagicMock()
    connect = MagicMock()
    views = ProjectBindingViews.for_window(window)
    character_row = 4
    plot_row = 7
    window.tblDebugPersos.selectionModel().currentIndex().row.return_value = (
        character_row
    )
    window.tblDebugPlots.selectionModel().currentIndex().row.return_value = (
        plot_row
    )
    binding = DebugProjectBinding(views.debug, runtime)

    binding.bind(connect)
    binding._show_current_character()
    binding._show_current_plot_characters()
    binding._show_current_plot_steps()

    window.tblDebugFlatData.setModel.assert_called_once_with(
        runtime.models.flat_data
    )
    window.treeDebugOutline.setModel.assert_called_once_with(
        runtime.models.outline
    )
    assert connect.call_count == 3
    runtime.models.characters.index.assert_called_once_with(
        character_row,
        Character.name,
    )
    runtime.models.plots.index.assert_any_call(plot_row, Plot.characters)
    runtime.models.plots.index.assert_any_call(plot_row, Plot.steps)
