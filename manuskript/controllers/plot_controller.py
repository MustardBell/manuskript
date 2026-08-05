from functools import partial

from PyQt5.QtCore import QModelIndex
from PyQt5.QtWidgets import QAction, QHeaderView, QMenu

from manuskript.enums import Plot, PlotStep
from manuskript.functions import toInt


class PlotController:
    """Coordinate plot data with plot-specific widgets and navigation.

    Takes the panel it drives, the models it edits, and the two services
    every panel needs, rather than a window that can answer anything.
    """

    def __init__(self, models, panel, navigation, dialogs):
        self.models = models
        self.panel = panel
        self.navigation = navigation
        self.dialogs = dialogs
        self._character_menu = None

    def reset(self):
        """Release UI objects whose actions target the current project."""
        self.panel.add_character_button.setMenu(None)
        if self._character_menu is not None:
            self._character_menu.deleteLater()
            self._character_menu = None

    def record_current_selection(self):
        plot_id = self.panel.plots.currentPlotID()
        self.navigation.record(
            ("plot", plot_id),
            selection_empty=plot_id is None,
        )

    def handle_plot_selection_changed(self, *_):
        index = self.panel.plots.currentPlotIndex()
        plot_id = self.panel.plots.currentPlotID()

        if not index.isValid():
            self._clear_current_plot()
            self.navigation.record(
                ("plot", None),
                selection_empty=True,
            )
            return

        self.navigation.record(("plot", plot_id), selection_empty=False)
        self.panel.tabs.setEnabled(True)

        for widget in self.panel.fields:
            widget.setCurrentModelIndex(index)

        characters_index = index.sibling(index.row(), Plot.characters)
        self.panel.characters.setRootIndex(characters_index)

        importance = self.models.plots.getPlotImportanceByRow(index.row())
        self.panel.importance_slider.setValue(int(importance))

        steps_index = index.sibling(index.row(), Plot.steps)
        self.panel.steps.setRootIndex(steps_index)
        if self.models.plots.rowCount(steps_index):
            self.configure_sub_plot_view()

        self.panel.step_summary.setCurrentModelIndex(QModelIndex())
        self.panel.characters.selectionModel().clear()
        self.handle_plot_character_selection()

    def _clear_current_plot(self):
        self.panel.tabs.setEnabled(False)
        invalid = QModelIndex()
        for widget in self.panel.fields + (self.panel.step_summary,):
            widget.setCurrentModelIndex(invalid)
        self.panel.characters.setRootIndex(invalid)
        self.panel.steps.setRootIndex(invalid)
        self.panel.remove_character_button.setEnabled(False)

    def configure_sub_plot_view(self):
        """Keep hidden step data intact while presenting editable columns."""
        header = self.panel.steps.horizontalHeader()
        header.setSectionResizeMode(PlotStep.ID, QHeaderView.Fixed)
        header.setSectionResizeMode(PlotStep.summary, QHeaderView.Fixed)
        header.resizeSection(PlotStep.ID, 0)
        header.resizeSection(PlotStep.summary, 0)
        header.setSectionResizeMode(PlotStep.name, QHeaderView.Stretch)
        header.setSectionResizeMode(
            PlotStep.meta,
            QHeaderView.ResizeToContents,
        )
        self.panel.steps.verticalHeader().hide()

    def change_current_sub_plot(self, index, *_):
        if index.isValid():
            index = index.sibling(index.row(), PlotStep.summary)
        self.panel.step_summary.setColumn(PlotStep.summary)
        self.panel.step_summary.setCurrentModelIndex(index)

    def add_plot(self, _checked=False):
        return self.models.plots.addPlot()

    def remove_current_plot(self, _checked=False):
        return self.models.plots.removePlot(
            self.panel.plots.currentPlotIndex()
        )

    def add_sub_plot(self, _checked=False):
        plot_index = self.panel.plots.currentPlotIndex()
        after_index = self.panel.steps.currentIndex()
        new_index = self.models.plots.addSubPlot(
            plot_index,
            after_index,
        )
        if new_index.isValid():
            self.configure_sub_plot_view()
            self.panel.steps.setCurrentIndex(new_index)
        return new_index

    def remove_selected_sub_plots(self, _checked=False):
        selection = self.panel.steps.selectionModel()
        rows = [index.row() for index in selection.selectedRows()]
        return self.models.plots.removeSubPlots(
            self.panel.steps.rootIndex(),
            rows,
        )

    def add_plot_character(self, character_id, _checked=False):
        return self.models.plots.addPlotPerso(
            self.panel.plots.currentPlotIndex(),
            character_id,
        )

    def remove_selected_plot_characters(self, _checked=False):
        indexes = self.panel.characters.selectionModel().selectedIndexes()
        return self.models.plots.removePlotPersos(indexes)

    def handle_plot_character_selection(self, *_):
        selection = self.panel.characters.selectionModel()
        self.panel.remove_character_button.setEnabled(
            bool(selection.selectedIndexes())
        )

    def refresh_character_menu(self, *_):
        """Rebuild the add-character menu from the character model."""
        menu = QMenu(self.dialogs.parent)
        categories = []
        for title in [
            self.dialogs.translate("Main"),
            self.dialogs.translate("Secondary"),
            self.dialogs.translate("Minor"),
        ]:
            category = QMenu(title, menu)
            categories.append(category)
            menu.addMenu(category)

        character_model = self.models.characters
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
        self.panel.add_character_button.setMenu(menu)
        if old_menu is not None:
            old_menu.deleteLater()
