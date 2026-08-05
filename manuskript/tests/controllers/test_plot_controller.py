from unittest.mock import MagicMock

from PyQt5.QtCore import QModelIndex

from manuskript.controllers.plot_controller import PlotController
from manuskript.enums import Plot
from manuskript.models.plotModel import plotModel
from manuskript.ui.views.plot_panel import PlotPanelView


def make_controller():
    """The panel it drives and the models it edits, named.

    A real plot model, because these tests are about coordinating one
    with the widgets around it; everything else is a double.
    """
    model = plotModel()
    model.addPlot("A plot")
    plot_index = model.index(0, Plot.name)
    models = MagicMock()
    models.plots = model
    panel = PlotPanelView(
        plots=MagicMock(),
        steps=MagicMock(),
        characters=MagicMock(),
        tabs=MagicMock(),
        add_character_button=MagicMock(),
        remove_character_button=MagicMock(),
        importance_slider=MagicMock(),
        step_summary=MagicMock(),
        fields=(MagicMock(), MagicMock(), MagicMock(), MagicMock()),
    )
    panel.plots.currentPlotIndex.return_value = plot_index
    panel.plots.currentPlotID.return_value = "0"
    navigation = MagicMock()
    dialogs = MagicMock()
    dialogs.translate.side_effect = lambda text: text
    controller = PlotController(models, panel, navigation, dialogs)
    return controller, panel, model, plot_index, navigation


def test_add_sub_plot_coordinates_model_and_view():
    controller, panel, model, plot_index, _nav = make_controller()
    panel.steps.currentIndex.return_value = QModelIndex()

    new_index = controller.add_sub_plot()

    assert new_index.isValid()
    assert model.rowCount(
        plot_index.sibling(plot_index.row(), Plot.steps)
    ) == 1
    panel.steps.setCurrentIndex.assert_called_once_with(new_index)
    panel.steps.verticalHeader.return_value.hide.assert_called_once_with()


def test_plot_selection_binds_fields_and_records_history():
    controller, panel, _model, plot_index, navigation = make_controller()

    controller.handle_plot_selection_changed()

    panel.tabs.setEnabled.assert_called_once_with(True)
    for widget in panel.fields:
        widget.setCurrentModelIndex.assert_called_once_with(plot_index)
    panel.characters.setRootIndex.assert_called_once_with(
        plot_index.sibling(plot_index.row(), Plot.characters)
    )
    # One statement rather than a push and a flag set across a boundary.
    navigation.record.assert_called_once_with(
        ("plot", "0"),
        selection_empty=False,
    )


def test_empty_plot_selection_clears_stale_bindings():
    controller, panel, _model, _plot_index, navigation = make_controller()
    panel.plots.currentPlotIndex.return_value = QModelIndex()
    panel.plots.currentPlotID.return_value = None

    controller.handle_plot_selection_changed()

    panel.tabs.setEnabled.assert_called_once_with(False)
    panel.characters.setRootIndex.assert_called_once()
    assert not panel.characters.setRootIndex.call_args.args[0].isValid()
    panel.steps.setRootIndex.assert_called_once()
    assert not panel.steps.setRootIndex.call_args.args[0].isValid()
    navigation.record.assert_called_once_with(
        ("plot", None),
        selection_empty=True,
    )


def test_character_associations_use_current_plot_and_explicit_selection():
    controller, panel, model, plot_index, _nav = make_controller()
    assert controller.add_plot_character("7")
    assert not controller.add_plot_character("7")

    characters_index = plot_index.sibling(
        plot_index.row(),
        Plot.characters,
    )
    selected = model.index(0, 0, characters_index)
    panel.characters.selectionModel.return_value.selectedIndexes\
        .return_value = [selected]

    assert controller.remove_selected_plot_characters() == 1
    assert model.rowCount(characters_index) == 0
