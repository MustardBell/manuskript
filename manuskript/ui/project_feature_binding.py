from manuskript import functions as F
from manuskript.enums import Character, Plot, PlotStep, World
from manuskript.ui.views.outlineDelegates import (
    outlineCharacterDelegate,
)
from manuskript.ui.views.plotDelegate import plotDelegate


class CharacterProjectBinding:
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
        controller = window.characterController
        controller.configure_info_view(window.tblPersoInfos)
        window.lstCharacters.setCharactersModel(models.characters)
        window.tblPersoInfos.setModel(models.characters)
        for signal, slot in [
            (
                window.btnAddPerso.clicked,
                window.lstCharacters.addCharacter,
            ),
            (
                window.btnRmPerso.clicked,
                controller.delete_characters,
            ),
            (
                window.btnPersoColor.clicked,
                controller.choose_character_color,
            ),
            (
                window.chkPersoPOV.stateChanged,
                controller.change_character_pov_state,
            ),
            (
                window.btnPersoAddInfo.clicked,
                controller.add_character_info,
            ),
            (
                window.btnPersoRmInfo.clicked,
                controller.remove_character_info,
            ),
        ]:
            connect(signal, slot, F.AUC)

        for widget, column in [
            (window.txtPersoName, Character.name),
            (window.sldPersoImportance, Character.importance),
            (window.txtPersoMotivation, Character.motivation),
            (window.txtPersoGoal, Character.goal),
            (window.txtPersoConflict, Character.conflict),
            (window.txtPersoEpiphany, Character.epiphany),
            (
                window.txtPersoSummarySentence,
                Character.summarySentence,
            ),
            (window.txtPersoSummaryPara, Character.summaryPara),
            (window.txtPersoSummaryFull, Character.summaryFull),
            (window.txtPersoNotes, Character.notes),
        ]:
            widget.setModel(models.characters)
            widget.setColumn(column)
        window.tabPersos.setEnabled(False)

    def unbind(self):
        self.window.characterController.reset()


class PlotProjectBinding:
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
        controller = window.plotController
        window.lstSubPlots.setModel(models.plots)
        window.lstPlotPerso.setModel(models.plots)
        window.lstPlots.setPlotModel(
            models.plots,
            settings=window.settingsManager,
        )
        for signal, slot in [
            (window.btnAddPlot.clicked, controller.add_plot),
            (window.btnRmPlot.clicked, controller.remove_current_plot),
            (window.btnAddSubPlot.clicked, controller.add_sub_plot),
            (
                window.btnRmSubPlot.clicked,
                controller.remove_selected_sub_plots,
            ),
            (
                window.lstPlotPerso.selectionModel().selectionChanged,
                controller.handle_plot_character_selection,
            ),
            (
                window.btnRmPlotPerso.clicked,
                controller.remove_selected_plot_characters,
            ),
            (
                window.lstSubPlots.selectionModel().currentRowChanged,
                controller.change_current_sub_plot,
            ),
        ]:
            connect(signal, slot, F.AUC)

        for widget, column in [
            (window.txtPlotName, Plot.name),
            (window.txtPlotDescription, Plot.description),
            (window.txtPlotResult, Plot.result),
            (window.sldPlotImportance, Plot.importance),
        ]:
            widget.setModel(models.plots)
            widget.setColumn(column)

        window.tabPlot.setEnabled(False)
        controller.refresh_character_menu()
        connect(
            models.characters.dataChanged,
            controller.refresh_character_menu,
        )
        window.lstOutlinePlots.setPlotModel(
            models.plots,
            settings=window.settingsManager,
        )
        window.lstOutlinePlots.setShowSubPlot(True)
        window.plotCharacterDelegate = outlineCharacterDelegate(
            models.characters,
            window,
        )
        window.lstPlotPerso.setItemDelegate(
            window.plotCharacterDelegate
        )
        window.plotDelegate = plotDelegate(window)
        window.lstSubPlots.setItemDelegateForColumn(
            PlotStep.meta,
            window.plotDelegate,
        )

    def unbind(self):
        self.window.plotController.reset()


class WorldProjectBinding:
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
        controller = window.worldController
        window.treeWorld.setModel(models.world)
        for column in range(models.world.columnCount()):
            window.treeWorld.hideColumn(column)
        window.treeWorld.showColumn(0)
        controller.build_data_set_menu()
        for signal, slot in [
            (
                window.treeWorld.selectionModel().selectionChanged,
                controller.handle_selection_changed,
            ),
            (window.btnAddWorld.clicked, controller.add_item),
            (
                window.btnRmWorld.clicked,
                controller.remove_selected_items,
            ),
        ]:
            connect(signal, slot, F.AUC)
        for widget, column in [
            (window.txtWorldName, World.name),
            (window.txtWorldDescription, World.description),
            (window.txtWorldPassion, World.passion),
            (window.txtWorldConflict, World.conflict),
        ]:
            widget.setModel(models.world)
            widget.setColumn(column)
        window.tabWorld.setEnabled(False)
        window.treeWorld.expandAll()

    def unbind(self):
        self.window.worldController.reset()


class ProjectFeatureBinding:
    """Composite lifecycle for independently bound project features."""

    def __init__(self, window, runtime):
        self.bindings = (
            CharacterProjectBinding(window, runtime),
            PlotProjectBinding(window, runtime),
            WorldProjectBinding(window, runtime),
        )
        self.bound = False

    def bind(self, connect):
        if self.bound:
            raise RuntimeError(
                "Project features must be released before rebinding."
            )
        installed = []
        try:
            for binding in self.bindings:
                binding.bind(connect)
                installed.append(binding)
        except Exception:
            for binding in reversed(installed):
                binding.unbind()
            raise
        self.bound = True

    def unbind(self):
        if not self.bound:
            return
        for binding in reversed(self.bindings):
            binding.unbind()
        self.bound = False
