from dataclasses import replace
from unittest.mock import MagicMock
from types import SimpleNamespace

from manuskript.enums import Character, Plot
from manuskript.panels.core import EDITOR, GENERAL, OUTLINE
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

    binding = FlatDataProjectBinding(views.flat_data, runtime)
    binding.bind(MagicMock())
    binding.attach_surface(SimpleNamespace(
        id=GENERAL,
        widget=window.corePanels.general,
    ))

    window.txtSummarySituation.setModel.assert_not_called()
    window.corePanels.general.email.setModel.assert_called_once_with(
        runtime.models.flat_data
    )
    window.corePanels.general.email.setColumn.assert_called_once_with(7)
    assert runtime.models.flat_data.index.call_count == 8
    runtime.models.flat_data.index.assert_any_call(0, 7)


def test_outline_selection_binding_registers_project_connections():
    window = MagicMock()
    runtime = MagicMock()
    connect = MagicMock()
    views = ProjectBindingViews.for_window(window)

    OutlineSelectionProjectBinding(views.outline_selection).bind(connect)

    assert connect.call_count == 3
    connected_slots = [call.args[1] for call in connect.call_args_list]
    assert (
        window.workspaceSelection.project_selection_changed
        in connected_slots
    )


def test_outline_selection_binding_needs_no_metadata_panel():
    window = MagicMock()
    window.corePanels.optional_tool.side_effect = (
        lambda name: getattr(window.corePanels, name)
    )
    views = ProjectBindingViews.for_window(window)
    sparse = replace(views.outline_selection, metadata=None)
    connect = MagicMock()

    OutlineSelectionProjectBinding(sparse).bind(connect)

    connect.assert_called_once()
    signal, slot, _connection_type = connect.call_args.args
    assert signal is sparse.project_tree.selectionModel().selectionChanged
    assert slot is sparse.project_tree_changed


def test_outline_and_editor_selection_connections_follow_their_surfaces():
    window = MagicMock()
    window.corePanels.optional_tool.side_effect = (
        lambda name: getattr(window.corePanels, name)
    )
    views = ProjectBindingViews.for_window(window)
    binding = OutlineSelectionProjectBinding(views.outline_selection)
    binding.bind(MagicMock())
    outline = SimpleNamespace(
        id=OUTLINE,
        widget=window.corePanels.outline,
    )
    editor = SimpleNamespace(
        id=EDITOR,
        widget=window.corePanels.editor,
    )

    binding.attach_surface(outline)
    binding.attach_surface(editor)

    (
        window.corePanels.outline.treeOutlineOutline.selectionModel()
        .selectionChanged.connect.assert_called()
    )
    project_signal = (
        window.corePanels.project_tree.tree.selectionModel()
        .selectionChanged
    )
    assert any(
        call.args[0] is window.corePanels.editor.editor.selectionChanged
        for call in project_signal.connect.call_args_list
    )

    binding.detach_surface(editor)
    project_signal.disconnect.assert_called()


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
