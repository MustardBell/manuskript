from manuskript import functions as F
from manuskript.enums import Character, Plot, PlotStep, World
from manuskript.ui.views.outlineDelegates import (
    outlineCharacterDelegate,
)
from manuskript.ui.views.plotDelegate import plotDelegate


class CharacterProjectBinding:
    def __init__(self, window):
        self.window = window

    def bind(self, connect):
        window = self.window
        controller = window.characterController
        controller.configure_info_view(window.tblPersoInfos)
        window.lstCharacters.setCharactersModel(window.mdlCharacter)
        window.tblPersoInfos.setModel(window.mdlCharacter)
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
            widget.setModel(window.mdlCharacter)
            widget.setColumn(column)
        window.tabPersos.setEnabled(False)

    def unbind(self):
        self.window.characterController.reset()


class PlotProjectBinding:
    def __init__(self, window):
        self.window = window

    def bind(self, connect):
        window = self.window
        controller = window.plotController
        window.lstSubPlots.setModel(window.mdlPlots)
        window.lstPlotPerso.setModel(window.mdlPlots)
        window.lstPlots.setPlotModel(
            window.mdlPlots,
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
            widget.setModel(window.mdlPlots)
            widget.setColumn(column)

        window.tabPlot.setEnabled(False)
        controller.refresh_character_menu()
        connect(
            window.mdlCharacter.dataChanged,
            controller.refresh_character_menu,
        )
        window.lstOutlinePlots.setPlotModel(
            window.mdlPlots,
            settings=window.settingsManager,
        )
        window.lstOutlinePlots.setShowSubPlot(True)
        window.plotCharacterDelegate = outlineCharacterDelegate(
            window.mdlCharacter,
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
    def __init__(self, window):
        self.window = window

    def bind(self, connect):
        window = self.window
        controller = window.worldController
        window.treeWorld.setModel(window.mdlWorld)
        for column in range(window.mdlWorld.columnCount()):
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
            widget.setModel(window.mdlWorld)
            widget.setColumn(column)
        window.tabWorld.setEnabled(False)
        window.treeWorld.expandAll()

    def unbind(self):
        self.window.worldController.reset()


class ProjectFeatureBinding:
    """Composite lifecycle for independently bound project features."""

    def __init__(self, window):
        self.bindings = (
            CharacterProjectBinding(window),
            PlotProjectBinding(window),
            WorldProjectBinding(window),
        )
        self.bound = False

    def bind(self, connect):
        if self.bound:
            raise RuntimeError(
                "Project features must be released before rebinding."
            )
        for binding in self.bindings:
            binding.bind(connect)
        self.bound = True

    def unbind(self):
        if not self.bound:
            return
        for binding in reversed(self.bindings):
            binding.unbind()
        self.bound = False
