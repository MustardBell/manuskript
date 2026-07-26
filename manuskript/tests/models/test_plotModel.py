from PyQt5.QtCore import QModelIndex

from manuskript.enums import Plot, PlotStep
from manuskript.models.plotModel import plotModel


def model_with_plot():
    model = plotModel()
    model.addPlot("A plot")
    return model, model.index(0, Plot.name)


def test_sub_plot_mutations_use_explicit_indexes():
    model, plot_index = model_with_plot()

    first = model.addSubPlot(plot_index)
    second = model.addSubPlot(plot_index)
    inserted = model.addSubPlot(plot_index, first)
    steps_index = plot_index.sibling(plot_index.row(), Plot.steps)

    assert first.isValid()
    assert second.isValid()
    assert inserted.row() == 1
    assert model.rowCount(steps_index) == 3
    assert [
        model.index(row, PlotStep.ID, steps_index).data()
        for row in range(3)
    ] == ["0", "2", "1"]

    assert model.removeSubPlots(steps_index, [0, 2, 2, 99]) == 2
    assert model.rowCount(steps_index) == 1
    assert model.index(0, PlotStep.ID, steps_index).data() == "2"


def test_sub_plot_queries_follow_the_steps_column():
    model, plot_index = model_with_plot()
    step_index = model.addSubPlot(plot_index)
    model.setData(
        step_index.sibling(step_index.row(), PlotStep.summary),
        "A summary",
    )

    assert model.getSubPlotTextsByID("0", 0) == (
        step_index.data(),
        "A summary",
    )
    assert model.getSubPlotTextsByID("missing", 0) == (None, None)


def test_plot_character_mutations_are_explicit_and_deduplicated():
    model, plot_index = model_with_plot()

    assert model.addPlotPerso(plot_index, "7")
    assert not model.addPlotPerso(plot_index, 7)
    assert model.addPlotPerso(plot_index, "8")

    characters_index = plot_index.sibling(
        plot_index.row(),
        Plot.characters,
    )
    character_indexes = [
        model.index(row, 0, characters_index)
        for row in range(model.rowCount(characters_index))
    ]

    assert model.removePlotPersos(character_indexes) == 2
    assert model.rowCount(characters_index) == 0
    assert model.removePlotPersos([QModelIndex()]) == 0


def test_remove_plot_rejects_invalid_and_nested_indexes():
    model, plot_index = model_with_plot()
    step_index = model.addSubPlot(plot_index)

    assert not model.removePlot(QModelIndex())
    assert not model.removePlot(step_index)
    assert model.rowCount() == 1
    assert model.removePlot(plot_index)
    assert model.rowCount() == 0
