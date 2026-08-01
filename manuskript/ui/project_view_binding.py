from manuskript import functions as F
from manuskript.enums import Character, Plot


class FlatDataProjectBinding:
    """Bind general-information and summary fields to flat project data."""

    def __init__(self, window):
        self.window = window

    def bind(self, _connect):
        window = self.window
        for widget, column in [
            (window.txtSummarySituation, 0),
            (window.txtSummarySentence, 1),
            (window.txtSummarySentence_2, 1),
            (window.txtSummaryPara, 2),
            (window.txtSummaryPara_2, 2),
            (window.txtPlotSummaryPara, 2),
            (window.txtSummaryPage, 3),
            (window.txtSummaryPage_2, 3),
            (window.txtPlotSummaryPage, 3),
            (window.txtSummaryFull, 4),
            (window.txtPlotSummaryFull, 4),
        ]:
            widget.setModel(window.mdlFlatData)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                window.mdlFlatData.index(1, column)
            )

        for widget, column in [
            (window.txtGeneralTitle, 0),
            (window.txtGeneralSubtitle, 1),
            (window.txtGeneralSerie, 2),
            (window.txtGeneralVolume, 3),
            (window.txtGeneralGenre, 4),
            (window.txtGeneralLicense, 5),
            (window.txtGeneralAuthor, 6),
            (window.txtGeneralEmail, 7),
        ]:
            widget.setModel(window.mdlFlatData)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                window.mdlFlatData.index(0, column)
            )


class OutlineSelectionProjectBinding:
    """Route outline selections to their project-scoped consumers."""

    def __init__(self, window):
        self.window = window

    def bind(self, connect):
        window = self.window
        for signal, slot in [
            (
                window.treeOutlineOutline.selectionModel().selectionChanged,
                window.outlineChanged,
            ),
            (
                window.treeOutlineOutline.selectionModel().selectionChanged,
                window.outlineItemEditor.selectionChanged,
            ),
            (
                window.treeOutlineOutline.clicked,
                window.outlineItemEditor.selectionChanged,
            ),
            (
                window.treeRedacOutline.selectionModel().selectionChanged,
                window.redacOutlineChanged,
            ),
            (
                window.treeRedacOutline.selectionModel().selectionChanged,
                window.redacMetadata.selectionChanged,
            ),
            (
                window.treeRedacOutline.clicked,
                window.redacMetadata.selectionChanged,
            ),
            (
                window.treeRedacOutline.selectionModel().selectionChanged,
                window.mainEditor.selectionChanged,
            ),
        ]:
            connect(signal, slot, F.AUC)


class DebugProjectBinding:
    """Bind the optional debug views to the active project models."""

    def __init__(self, window):
        self.window = window

    def bind(self, connect):
        window = self.window
        window.mdlFlatData.setVerticalHeaderLabels(
            ["General info", "Summary"]
        )
        window.tblDebugFlatData.setModel(window.mdlFlatData)
        window.tblDebugPersos.setModel(window.mdlCharacter)
        window.tblDebugPersosInfos.setModel(window.mdlCharacter)
        connect(
            window.tblDebugPersos.selectionModel().currentChanged,
            self._show_current_character,
            F.AUC,
        )

        window.tblDebugPlots.setModel(window.mdlPlots)
        window.tblDebugPlotsPersos.setModel(window.mdlPlots)
        window.tblDebugSubPlots.setModel(window.mdlPlots)
        connect(
            window.tblDebugPlots.selectionModel().currentChanged,
            self._show_current_plot_characters,
            F.AUC,
        )
        connect(
            window.tblDebugPlots.selectionModel().currentChanged,
            self._show_current_plot_steps,
            F.AUC,
        )
        window.treeDebugWorld.setModel(window.mdlWorld)
        window.treeDebugOutline.setModel(window.mdlOutline)
        window.lstDebugLabels.setModel(window.mdlLabels)
        window.lstDebugStatus.setModel(window.mdlStatus)

    def _show_current_character(self, *_args):
        window = self.window
        window.tblDebugPersosInfos.setRootIndex(
            window.mdlCharacter.index(
                window.tblDebugPersos.selectionModel().currentIndex().row(),
                Character.name,
            )
        )

    def _show_current_plot_characters(self, *_args):
        window = self.window
        window.tblDebugPlotsPersos.setRootIndex(
            window.mdlPlots.index(
                window.tblDebugPlots.selectionModel().currentIndex().row(),
                Plot.characters,
            )
        )

    def _show_current_plot_steps(self, *_args):
        window = self.window
        window.tblDebugSubPlots.setRootIndex(
            window.mdlPlots.index(
                window.tblDebugPlots.selectionModel().currentIndex().row(),
                Plot.steps,
            )
        )
