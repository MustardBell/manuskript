from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QLabel,
    QLineEdit,
    QListView,
    QTableView,
    QTextEdit,
)

from manuskript.enums import (
    Character,
    FlatData,
    Model,
    Outline,
    Plot,
    PlotStep,
    World,
)
from manuskript.models import references
from manuskript.models.flatDataModelWrapper import flatDataModelWrapper


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


class SearchResultViewAdapter:
    """Expose search-result UI operations without global window lookup."""

    def __init__(self, window, reference_service):
        self.window = window
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
        self.references.open(references.characterReference(result.id()))
        self.window.tabPersos.setEnabled(True)

    def _open_flat_data(self, _result):
        self.window.tabMain.setCurrentIndex(self.window.TabSummary)

    def _open_outline(self, result):
        self.references.open(references.textReference(result.id()))

    def _open_world(self, result):
        self.references.open(references.worldReference(result.id()))
        self.window.tabWorld.setEnabled(True)

    def _open_plot(self, result):
        self.references.open(references.plotReference(result.id()))
        self.window.tabPlot.setEnabled(True)

    def _character_widgets(self, result):
        targets = {
            Character.name: (0, "txtPersoName", QLineEdit),
            Character.goal: (0, "txtPersoGoal", QTextEdit),
            Character.motivation: (0, "txtPersoMotivation", QTextEdit),
            Character.conflict: (0, "txtPersoConflict", QTextEdit),
            Character.epiphany: (0, "txtPersoEpiphany", QTextEdit),
            Character.summarySentence: (
                0,
                "txtPersoSummarySentence",
                QTextEdit,
            ),
            Character.summaryPara: (0, "txtPersoSummaryPara", QTextEdit),
            Character.summaryFull: (1, "txtPersoSummaryFull", QTextEdit),
            Character.notes: (2, "txtPersoNotes", QTextEdit),
            Character.infos: (3, "tblPersoInfos", QTableView),
        }
        tab_index, name, widget_type = targets[result.column()]
        self.window.tabPersos.setCurrentIndex(tab_index)
        return self.window.tabPersos.findChild(widget_type, name)

    def _flat_data_widgets(self, result):
        targets = {
            FlatData.summarySituation: (
                0,
                "txtSummarySituation",
                QLineEdit,
                self.window,
            ),
            FlatData.summarySentence: (
                0,
                "txtSummarySentence",
                QTextEdit,
                self.window.tabSummary,
            ),
            FlatData.summaryPara: (
                1,
                "txtSummaryPara",
                QTextEdit,
                self.window.tabSummary,
            ),
            FlatData.summaryPage: (
                2,
                "txtSummaryPage",
                QTextEdit,
                self.window.tabSummary,
            ),
            FlatData.summaryFull: (
                3,
                "txtSummaryFull",
                QTextEdit,
                self.window.tabSummary,
            ),
        }
        tab_index, name, widget_type, root = targets[result.column()]
        self.window.tabSummary.setCurrentIndex(tab_index)
        return root.findChild(widget_type, name)

    def _outline_widgets(self, result):
        targets = {
            Outline.text: ("txtRedacText", QTextEdit, False),
            Outline.title: ("txtTitle", QLineEdit, True),
            Outline.summarySentence: ("txtSummarySentence", QLineEdit, True),
            Outline.summaryFull: ("txtSummaryFull", QTextEdit, True),
            Outline.notes: ("txtNotes", QTextEdit, True),
            Outline.POV: ("lblPOV", QLabel, True),
            Outline.status: ("lblStatus", QLabel, True),
            Outline.label: ("lblLabel", QLabel, True),
        }
        name, widget_type, is_metadata = targets[result.column()]
        if is_metadata:
            metadata = self.window.corePanels.metadata
            # Through the panel's own action, so the toolbar button that
            # mirrors it stays in agreement.
            self.window.panelHost.set_visible("core.metadata")
            return metadata.findChild(widget_type, name)
        editor = self.window.mainEditor.currentEditor()
        return editor.findChild(widget_type, name)

    def _world_widgets(self, result):
        targets = {
            World.name: (0, "txtWorldName", QLineEdit),
            World.description: (0, "txtWorldDescription", QTextEdit),
            World.passion: (1, "txtWorldPassion", QTextEdit),
            World.conflict: (1, "txtWorldConflict", QTextEdit),
        }
        tab_index, name, widget_type = targets[result.column()]
        self.window.tabWorld.setCurrentIndex(tab_index)
        return self.window.tabWorld.findChild(widget_type, name)

    def _plot_widgets(self, result):
        targets = {
            Plot.name: (0, "txtPlotName", QLineEdit),
            Plot.description: (0, "txtPlotDescription", QTextEdit),
            Plot.characters: (0, "lstPlotPerso", QListView),
            Plot.result: (0, "txtPlotResult", QTextEdit),
        }
        tab_index, name, widget_type = targets[result.column()]
        self.window.tabPlot.setCurrentIndex(tab_index)
        return self.window.tabPlot.findChild(widget_type, name)

    def _plot_step_widgets(self, result):
        targets = {
            PlotStep.name: [(1, "lstSubPlots", QTableView)],
            PlotStep.meta: [(1, "lstSubPlots", QTableView)],
            PlotStep.summary: [
                (1, "lstSubPlots", QTableView),
                (1, "txtSubPlotSummary", QTextEdit),
            ],
        }
        widgets = []
        for tab_index, name, widget_type in targets[result.column()]:
            self.window.tabPlot.setCurrentIndex(tab_index)
            widgets.append(
                self.window.tabPlot.findChild(widget_type, name)
            )
        return widgets
