"""The widgets and models the plot panel is made of."""

from dataclasses import dataclass
from typing import Any, Tuple


class PlotModels:
    """The two models the plot panel works with.

    Read from the project runtime whenever asked: the panel is built once
    and the models under it are replaced with every project.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    @property
    def plots(self):
        return self._runtime.models.plots

    @property
    def characters(self):
        return self._runtime.models.characters


@dataclass(frozen=True)
class PlotPanelView:
    """One window's plot panel."""

    #: The list of plots, which owns the selection.
    plots: Any
    #: The steps of the selected plot.
    steps: Any
    #: The characters taking part in the selected plot.
    characters: Any
    #: The tab area holding the selected plot's detail views.
    tabs: Any
    #: Opens the menu of characters that can be added.
    add_character_button: Any
    remove_character_button: Any
    importance_slider: Any
    step_summary: Any
    add_plot_button: Any
    remove_plot_button: Any
    add_step_button: Any
    remove_step_button: Any
    #: The outline-side plot list, which shares the plot model.
    outline_plots: Any
    #: Every field bound to the selected plot's model index.
    fields: Tuple[Any, ...]

    @classmethod
    def for_window(cls, window):
        """This window's plot widgets, read off it once."""
        return cls(
            plots=window.lstPlots,
            steps=window.lstSubPlots,
            characters=window.lstPlotPerso,
            tabs=window.tabPlot,
            add_character_button=window.btnAddPlotPerso,
            remove_character_button=window.btnRmPlotPerso,
            importance_slider=window.sldPlotImportance,
            step_summary=window.txtSubPlotSummary,
            fields=(
                window.txtPlotName,
                window.txtPlotDescription,
                window.txtPlotResult,
                window.sldPlotImportance,
            ),
            add_plot_button=window.btnAddPlot,
            remove_plot_button=window.btnRmPlot,
            add_step_button=window.btnAddSubPlot,
            remove_step_button=window.btnRmSubPlot,
            outline_plots=window.lstOutlinePlots,
        )
