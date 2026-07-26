from unittest.mock import MagicMock

from PyQt5.QtCore import QModelIndex

from manuskript.controllers.plot_controller import PlotController
from manuskript.enums import Plot
from manuskript.models.plotModel import plotModel


def make_controller():
    window = MagicMock()
    window.tr.side_effect = lambda text: text
    model = plotModel()
    model.addPlot("A plot")
    plot_index = model.index(0, Plot.name)
    window.mdlPlots = model
    window.lstPlots.currentPlotIndex.return_value = plot_index
    window.lstPlots.currentPlotID.return_value = "0"
    return PlotController(window), window, model, plot_index


def test_add_sub_plot_coordinates_model_and_view():
    controller, window, model, plot_index = make_controller()
    window.lstSubPlots.currentIndex.return_value = QModelIndex()

    new_index = controller.add_sub_plot()

    assert new_index.isValid()
    assert model.rowCount(
        plot_index.sibling(plot_index.row(), Plot.steps)
    ) == 1
    window.lstSubPlots.setCurrentIndex.assert_called_once_with(new_index)
    window.lstSubPlots.verticalHeader.return_value.hide.assert_called_once_with()


def test_plot_selection_binds_fields_and_records_history():
    controller, window, _model, plot_index = make_controller()

    controller.handle_plot_selection_changed()

    window.tabPlot.setEnabled.assert_called_once_with(True)
    for widget in [
        window.txtPlotName,
        window.txtPlotDescription,
        window.txtPlotResult,
        window.sldPlotImportance,
    ]:
        widget.setCurrentModelIndex.assert_called_once_with(plot_index)
    window.lstPlotPerso.setRootIndex.assert_called_once_with(
        plot_index.sibling(plot_index.row(), Plot.characters)
    )
    window.pushHistory.assert_called_once_with(("plot", "0"))
    assert window._previousSelectionEmpty is False


def test_empty_plot_selection_clears_stale_bindings():
    controller, window, _model, _plot_index = make_controller()
    window.lstPlots.currentPlotIndex.return_value = QModelIndex()
    window.lstPlots.currentPlotID.return_value = None

    controller.handle_plot_selection_changed()

    window.tabPlot.setEnabled.assert_called_once_with(False)
    window.lstPlotPerso.setRootIndex.assert_called_once()
    assert not window.lstPlotPerso.setRootIndex.call_args.args[0].isValid()
    window.lstSubPlots.setRootIndex.assert_called_once()
    assert not window.lstSubPlots.setRootIndex.call_args.args[0].isValid()
    window.pushHistory.assert_called_once_with(("plot", None))
    assert window._previousSelectionEmpty is True


def test_character_associations_use_current_plot_and_explicit_selection():
    controller, window, model, plot_index = make_controller()
    assert controller.add_plot_character("7")
    assert not controller.add_plot_character("7")

    characters_index = plot_index.sibling(
        plot_index.row(),
        Plot.characters,
    )
    selected = model.index(0, 0, characters_index)
    window.lstPlotPerso.selectionModel.return_value.selectedIndexes.return_value = [
        selected
    ]

    assert controller.remove_selected_plot_characters() == 1
    assert model.rowCount(characters_index) == 0
