from functools import partial

from PyQt5.QtCore import QModelIndex
from PyQt5.QtWidgets import QAction, QHeaderView, QMenu

from manuskript.enums import Plot, PlotStep
from manuskript.functions import toInt


class PlotController:
    """Coordinate plot data with plot-specific widgets and navigation."""

    def __init__(self, window):
        self.window = window
        self._character_menu = None

    def reset(self):
        """Release UI objects whose actions target the current project."""
        self.window.btnAddPlotPerso.setMenu(None)
        if self._character_menu is not None:
            self._character_menu.deleteLater()
            self._character_menu = None

    def record_current_selection(self):
        plot_id = self.window.lstPlots.currentPlotID()
        self.window.pushHistory(("plot", plot_id))
        self.window._previousSelectionEmpty = plot_id is None

    def handle_plot_selection_changed(self, *_):
        index = self.window.lstPlots.currentPlotIndex()
        plot_id = self.window.lstPlots.currentPlotID()

        if not index.isValid():
            self._clear_current_plot()
            self.window.pushHistory(("plot", None))
            self.window._previousSelectionEmpty = True
            return

        self.window.pushHistory(("plot", plot_id))
        self.window._previousSelectionEmpty = False
        self.window.tabPlot.setEnabled(True)

        for widget in [
            self.window.txtPlotName,
            self.window.txtPlotDescription,
            self.window.txtPlotResult,
            self.window.sldPlotImportance,
        ]:
            widget.setCurrentModelIndex(index)

        characters_index = index.sibling(index.row(), Plot.characters)
        self.window.lstPlotPerso.setRootIndex(characters_index)

        importance = self.window.mdlPlots.getPlotImportanceByRow(index.row())
        self.window.sldPlotImportance.setValue(int(importance))

        steps_index = index.sibling(index.row(), Plot.steps)
        self.window.lstSubPlots.setRootIndex(steps_index)
        if self.window.mdlPlots.rowCount(steps_index):
            self.configure_sub_plot_view()

        self.window.txtSubPlotSummary.setCurrentModelIndex(QModelIndex())
        self.window.lstPlotPerso.selectionModel().clear()
        self.handle_plot_character_selection()

    def _clear_current_plot(self):
        self.window.tabPlot.setEnabled(False)
        invalid = QModelIndex()
        for widget in [
            self.window.txtPlotName,
            self.window.txtPlotDescription,
            self.window.txtPlotResult,
            self.window.sldPlotImportance,
            self.window.txtSubPlotSummary,
        ]:
            widget.setCurrentModelIndex(invalid)
        self.window.lstPlotPerso.setRootIndex(invalid)
        self.window.lstSubPlots.setRootIndex(invalid)
        self.window.btnRmPlotPerso.setEnabled(False)

    def configure_sub_plot_view(self):
        """Keep hidden step data intact while presenting editable columns."""
        header = self.window.lstSubPlots.horizontalHeader()
        header.setSectionResizeMode(PlotStep.ID, QHeaderView.Fixed)
        header.setSectionResizeMode(PlotStep.summary, QHeaderView.Fixed)
        header.resizeSection(PlotStep.ID, 0)
        header.resizeSection(PlotStep.summary, 0)
        header.setSectionResizeMode(PlotStep.name, QHeaderView.Stretch)
        header.setSectionResizeMode(
            PlotStep.meta,
            QHeaderView.ResizeToContents,
        )
        self.window.lstSubPlots.verticalHeader().hide()

    def change_current_sub_plot(self, index, *_):
        if index.isValid():
            index = index.sibling(index.row(), PlotStep.summary)
        self.window.txtSubPlotSummary.setColumn(PlotStep.summary)
        self.window.txtSubPlotSummary.setCurrentModelIndex(index)

    def add_plot(self, _checked=False):
        return self.window.mdlPlots.addPlot()

    def remove_current_plot(self, _checked=False):
        return self.window.mdlPlots.removePlot(
            self.window.lstPlots.currentPlotIndex()
        )

    def add_sub_plot(self, _checked=False):
        plot_index = self.window.lstPlots.currentPlotIndex()
        after_index = self.window.lstSubPlots.currentIndex()
        new_index = self.window.mdlPlots.addSubPlot(
            plot_index,
            after_index,
        )
        if new_index.isValid():
            self.configure_sub_plot_view()
            self.window.lstSubPlots.setCurrentIndex(new_index)
        return new_index

    def remove_selected_sub_plots(self, _checked=False):
        selection = self.window.lstSubPlots.selectionModel()
        rows = [index.row() for index in selection.selectedRows()]
        return self.window.mdlPlots.removeSubPlots(
            self.window.lstSubPlots.rootIndex(),
            rows,
        )

    def add_plot_character(self, character_id, _checked=False):
        return self.window.mdlPlots.addPlotPerso(
            self.window.lstPlots.currentPlotIndex(),
            character_id,
        )

    def remove_selected_plot_characters(self, _checked=False):
        indexes = self.window.lstPlotPerso.selectionModel().selectedIndexes()
        return self.window.mdlPlots.removePlotPersos(indexes)

    def handle_plot_character_selection(self, *_):
        selection = self.window.lstPlotPerso.selectionModel()
        self.window.btnRmPlotPerso.setEnabled(
            bool(selection.selectedIndexes())
        )

    def refresh_character_menu(self, *_):
        """Rebuild the add-character menu from the character model."""
        menu = QMenu(self.window)
        categories = []
        for title in [
            self.window.tr("Main"),
            self.window.tr("Secondary"),
            self.window.tr("Minor"),
        ]:
            category = QMenu(title, menu)
            categories.append(category)
            menu.addMenu(category)

        character_model = self.window.mdlCharacter
        for row in range(character_model.rowCount()):
            action = QAction(character_model.name(row), menu)
            action.setIcon(character_model.icon(row))
            character_id = character_model.ID(row)
            action.triggered.connect(
                partial(self.add_plot_character, character_id)
            )

            importance = max(
                0,
                min(2, toInt(character_model.importance(row))),
            )
            categories[2 - importance].addAction(action)

        for category in categories:
            category.setEnabled(bool(category.actions()))

        old_menu = self._character_menu
        self._character_menu = menu
        self.window.btnAddPlotPerso.setMenu(menu)
        if old_menu is not None:
            old_menu.deleteLater()
