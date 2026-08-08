from manuskript import functions as F
from manuskript.enums import Character, Plot


class FlatDataProjectBinding:
    """Bind general-information and summary fields to flat project data."""

    def __init__(self, window, runtime):
        self.window = window
        self._runtime = runtime

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, _connect):
        window = self.window
        models = self.models
        book_summary = window.corePanels.book_summary
        for widget, column in [
            (window.txtSummarySituation, 0),
            (window.txtSummarySentence, 1),
            (window.txtSummarySentence_2, 1),
            (window.txtSummaryPara, 2),
            (window.txtSummaryPara_2, 2),
            (book_summary.paragraph_editor, 2),
            (window.txtSummaryPage, 3),
            (window.txtSummaryPage_2, 3),
            (book_summary.page_editor, 3),
            (window.txtSummaryFull, 4),
            (book_summary.full_editor, 4),
        ]:
            widget.setModel(models.flat_data)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                models.flat_data.index(1, column)
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
            widget.setModel(models.flat_data)
            widget.setColumn(column)
            widget.setCurrentModelIndex(
                models.flat_data.index(0, column)
            )


class OutlineSelectionProjectBinding:
    """Route outline selections to their project-scoped consumers."""

    def __init__(self, window, runtime):
        self.window = window
        self._runtime = runtime

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, connect):
        window = self.window
        models = self.models
        project_tree = window.corePanels.project_tree.tree
        metadata = window.corePanels.metadata
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
                project_tree.selectionModel().selectionChanged,
                window.redacOutlineChanged,
            ),
            (
                project_tree.selectionModel().selectionChanged,
                metadata.selectionChanged,
            ),
            (
                project_tree.clicked,
                metadata.selectionChanged,
            ),
            (
                project_tree.selectionModel().selectionChanged,
                window.mainEditor.selectionChanged,
            ),
        ]:
            connect(signal, slot, F.AUC)


class DebugProjectBinding:
    """Bind the optional debug views to the active project models."""

    def __init__(self, window, runtime):
        self.window = window
        self._runtime = runtime

    @property
    def models(self):
        """The project's models, from the runtime that owns them."""
        return self._runtime.models

    def bind(self, connect):
        window = self.window
        models = self.models
        models.flat_data.setVerticalHeaderLabels(
            ["General info", "Summary"]
        )
        window.tblDebugFlatData.setModel(models.flat_data)
        window.tblDebugPersos.setModel(models.characters)
        window.tblDebugPersosInfos.setModel(models.characters)
        connect(
            window.tblDebugPersos.selectionModel().currentChanged,
            self._show_current_character,
            F.AUC,
        )

        window.tblDebugPlots.setModel(models.plots)
        window.tblDebugPlotsPersos.setModel(models.plots)
        window.tblDebugSubPlots.setModel(models.plots)
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
        window.treeDebugWorld.setModel(models.world)
        window.treeDebugOutline.setModel(models.outline)
        window.lstDebugLabels.setModel(models.labels)
        window.lstDebugStatus.setModel(models.statuses)

    def _show_current_character(self, *_args):
        window = self.window
        models = self.models
        window.tblDebugPersosInfos.setRootIndex(
            models.characters.index(
                window.tblDebugPersos.selectionModel().currentIndex().row(),
                Character.name,
            )
        )

    def _show_current_plot_characters(self, *_args):
        window = self.window
        models = self.models
        window.tblDebugPlotsPersos.setRootIndex(
            models.plots.index(
                window.tblDebugPlots.selectionModel().currentIndex().row(),
                Plot.characters,
            )
        )

    def _show_current_plot_steps(self, *_args):
        window = self.window
        models = self.models
        window.tblDebugSubPlots.setRootIndex(
            models.plots.index(
                window.tblDebugPlots.selectionModel().currentIndex().row(),
                Plot.steps,
            )
        )
