from dataclasses import dataclass
from functools import partial
from types import MappingProxyType
from typing import Any, Callable, Mapping, Tuple

from manuskript.enums import (
    Character,
    FlatData,
    Model,
    Outline,
    Plot,
    PlotStep,
    World,
)
from manuskript.models.reference_identity import (
    character_reference,
    plot_reference,
    text_reference,
    world_reference,
)
from manuskript.models.flatDataModelWrapper import flatDataModelWrapper
from manuskript.panels.core import METADATA


@dataclass(frozen=True)
class SearchContext:
    """Project-scoped search models and result presentation."""

    outline: object
    characters: object
    flat_data: object
    world: object
    plots: object
    result_views: object

    @classmethod
    def from_models(
        cls,
        outline,
        characters,
        flat_data,
        world,
        plots,
        result_views,
    ):
        return cls(
            outline=outline,
            characters=characters,
            flat_data=flatDataModelWrapper(flat_data),
            world=world,
            plots=plots,
            result_views=result_views,
        )

    def sources(self):
        return (
            (self.outline, Model.Outline),
            (self.characters, Model.Character),
            (self.flat_data, Model.FlatData),
            (self.world, Model.World),
            (self.plots, Model.Plot),
        )


@dataclass(frozen=True)
class SearchResultViews:
    """Widgets search results may reveal or highlight in one workspace."""

    main_tabs: Any
    summary_tab_index: int
    character_tabs: Any
    summary_tabs: Any
    world_tabs: Any
    plot_tabs: Any
    character_fields: Mapping[int, Tuple[int, Any]]
    summary_fields: Mapping[int, Tuple[int, Any]]
    metadata_fields: Mapping[int, Any]
    world_fields: Mapping[int, Tuple[int, Any]]
    plot_fields: Mapping[int, Tuple[int, Any]]
    plot_step_fields: Mapping[int, Tuple[Any, ...]]
    current_document_text: Callable[[], Any]
    show_metadata: Callable[[], None]

    @classmethod
    def for_window(cls, window):
        metadata = window.corePanels.metadata
        properties = metadata.properties
        plot_steps = window.lstSubPlots
        main_editor = window.mainEditor
        panel_host = window.panelHost
        return cls(
            main_tabs=window.tabMain,
            summary_tab_index=window.TabSummary,
            character_tabs=window.tabPersos,
            summary_tabs=window.tabSummary,
            world_tabs=window.tabWorld,
            plot_tabs=window.tabPlot,
            character_fields=MappingProxyType({
                Character.name: (0, window.txtPersoName),
                Character.goal: (0, window.txtPersoGoal),
                Character.motivation: (0, window.txtPersoMotivation),
                Character.conflict: (0, window.txtPersoConflict),
                Character.epiphany: (0, window.txtPersoEpiphany),
                Character.summarySentence: (
                    0, window.txtPersoSummarySentence,
                ),
                Character.summaryPara: (0, window.txtPersoSummaryPara),
                Character.summaryFull: (1, window.txtPersoSummaryFull),
                Character.notes: (2, window.txtPersoNotes),
                Character.infos: (3, window.tblPersoInfos),
            }),
            summary_fields=MappingProxyType({
                FlatData.summarySituation: (0, window.txtSummarySituation),
                FlatData.summarySentence: (0, window.txtSummarySentence),
                FlatData.summaryPara: (1, window.txtSummaryPara),
                FlatData.summaryPage: (2, window.txtSummaryPage),
                FlatData.summaryFull: (3, window.txtSummaryFull),
            }),
            metadata_fields=MappingProxyType({
                Outline.title: properties.txtTitle,
                Outline.summarySentence: metadata.txtSummarySentence,
                Outline.summaryFull: metadata.txtSummaryFull,
                Outline.notes: metadata.txtNotes,
                Outline.POV: properties.lblPOV,
                Outline.status: properties.lblStatus,
                Outline.label: properties.lblLabel,
            }),
            world_fields=MappingProxyType({
                World.name: (0, window.txtWorldName),
                World.description: (0, window.txtWorldDescription),
                World.passion: (1, window.txtWorldPassion),
                World.conflict: (1, window.txtWorldConflict),
            }),
            plot_fields=MappingProxyType({
                Plot.name: (0, window.txtPlotName),
                Plot.description: (0, window.txtPlotDescription),
                Plot.characters: (0, window.lstPlotPerso),
                Plot.result: (0, window.txtPlotResult),
            }),
            plot_step_fields=MappingProxyType({
                PlotStep.name: (plot_steps,),
                PlotStep.meta: (plot_steps,),
                PlotStep.summary: (plot_steps, window.txtSubPlotSummary),
            }),
            current_document_text=lambda: (
                main_editor.currentEditor().txtRedacText
            ),
            show_metadata=partial(panel_host.set_visible, METADATA),
        )


class SearchResultViewAdapter:
    """Expose search-result UI operations without global window lookup."""

    def __init__(self, views, reference_service):
        self.views = views
        self.references = reference_service

    def open_result(self, result):
        handlers = {
            Model.Character: self._open_character,
            Model.FlatData: self._open_flat_data,
            Model.Outline: self._open_outline,
            Model.World: self._open_world,
            Model.Plot: self._open_plot,
            Model.PlotStep: self._open_plot,
        }
        handler = handlers.get(result.type())
        if handler is None:
            raise NotImplementedError(
                "Unsupported search result type: {}".format(result.type())
            )
        handler(result)

    def widgets_for(self, result):
        handlers = {
            Model.Character: self._character_widgets,
            Model.FlatData: self._flat_data_widgets,
            Model.Outline: self._outline_widgets,
            Model.World: self._world_widgets,
            Model.Plot: self._plot_widgets,
            Model.PlotStep: self._plot_step_widgets,
        }
        handler = handlers.get(result.type())
        if handler is None:
            raise NotImplementedError(
                "Unsupported search result type: {}".format(result.type())
            )
        widgets = handler(result)
        return widgets if isinstance(widgets, list) else [widgets]

    def _open_character(self, result):
        self.references.open(character_reference(result.id()))
        self.views.character_tabs.setEnabled(True)

    def _open_flat_data(self, _result):
        self.views.main_tabs.setCurrentIndex(self.views.summary_tab_index)

    def _open_outline(self, result):
        self.references.open(text_reference(result.id()))

    def _open_world(self, result):
        self.references.open(world_reference(result.id()))
        self.views.world_tabs.setEnabled(True)

    def _open_plot(self, result):
        self.references.open(plot_reference(result.id()))
        self.views.plot_tabs.setEnabled(True)

    def _character_widgets(self, result):
        tab_index, widget = self.views.character_fields[result.column()]
        self.views.character_tabs.setCurrentIndex(tab_index)
        return widget

    def _flat_data_widgets(self, result):
        tab_index, widget = self.views.summary_fields[result.column()]
        self.views.summary_tabs.setCurrentIndex(tab_index)
        return widget

    def _outline_widgets(self, result):
        if result.column() != Outline.text:
            # Through the panel's own action, so the toolbar button that
            # mirrors it stays in agreement.
            self.views.show_metadata()
            return self.views.metadata_fields[result.column()]
        return self.views.current_document_text()

    def _world_widgets(self, result):
        tab_index, widget = self.views.world_fields[result.column()]
        self.views.world_tabs.setCurrentIndex(tab_index)
        return widget

    def _plot_widgets(self, result):
        tab_index, widget = self.views.plot_fields[result.column()]
        self.views.plot_tabs.setCurrentIndex(tab_index)
        return widget

    def _plot_step_widgets(self, result):
        self.views.plot_tabs.setCurrentIndex(1)
        return list(self.views.plot_step_fields[result.column()])
