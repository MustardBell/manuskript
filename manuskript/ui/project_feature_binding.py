from manuskript import functions as F
from manuskript.enums import Character, Plot, PlotStep, World
from manuskript.ui.views.outlineDelegates import (
    outlineCharacterDelegate,
)
from manuskript.ui.views.plotDelegate import plotDelegate


class CharacterProjectBinding:
    def __init__(self, controller):
        self.controller = controller
        self.panel = controller.panel

    @property
    def models(self):
        """The current project's models through the controller facade."""
        return self.controller.models

    def bind(self, connect):
        panel = self.panel
        models = self.models
        controller = self.controller
        controller.configure_info_view(panel.info)
        panel.characters.setCharactersModel(models.characters)
        panel.info.setModel(models.characters)
        for signal, slot in [
            (
                panel.add_character_button.clicked,
                panel.characters.addCharacter,
            ),
            (
                panel.remove_character_button.clicked,
                controller.delete_characters,
            ),
            (
                panel.color_button.clicked,
                controller.choose_character_color,
            ),
            (
                panel.pov_checkbox.stateChanged,
                controller.change_character_pov_state,
            ),
            (
                panel.add_info_button.clicked,
                controller.add_character_info,
            ),
            (
                panel.remove_info_button.clicked,
                controller.remove_character_info,
            ),
        ]:
            connect(signal, slot, F.AUC)

        columns = (
            Character.name,
            Character.importance,
            Character.motivation,
            Character.goal,
            Character.conflict,
            Character.epiphany,
            Character.summarySentence,
            Character.summaryPara,
            Character.summaryFull,
            Character.notes,
        )
        if len(panel.fields) != len(columns):
            raise ValueError("Character panel field contract is incomplete.")
        for widget, column in zip(panel.fields, columns):
            widget.setModel(models.characters)
            widget.setColumn(column)
        panel.tabs.setEnabled(False)

    def unbind(self):
        self.controller.reset()


class PlotProjectBinding:
    def __init__(self, controller, settings):
        self.controller = controller
        self.panel = controller.panel
        self.settings = settings
        self._character_delegate = None
        self._step_delegate = None

    @property
    def models(self):
        """The current project's models through the controller facade."""
        return self.controller.models

    def bind(self, connect):
        panel = self.panel
        models = self.models
        controller = self.controller
        panel.steps.setModel(models.plots)
        panel.characters.setModel(models.plots)
        panel.plots.setPlotModel(
            models.plots,
            settings=self.settings,
        )
        for signal, slot in [
            (panel.add_plot_button.clicked, controller.add_plot),
            (panel.remove_plot_button.clicked, controller.remove_current_plot),
            (panel.add_step_button.clicked, controller.add_sub_plot),
            (
                panel.remove_step_button.clicked,
                controller.remove_selected_sub_plots,
            ),
            (
                panel.characters.selectionModel().selectionChanged,
                controller.handle_plot_character_selection,
            ),
            (
                panel.remove_character_button.clicked,
                controller.remove_selected_plot_characters,
            ),
            (
                panel.steps.selectionModel().currentRowChanged,
                controller.change_current_sub_plot,
            ),
        ]:
            connect(signal, slot, F.AUC)

        columns = (
            Plot.name,
            Plot.description,
            Plot.result,
            Plot.importance,
        )
        if len(panel.fields) != len(columns):
            raise ValueError("Plot panel field contract is incomplete.")
        for widget, column in zip(panel.fields, columns):
            widget.setModel(models.plots)
            widget.setColumn(column)

        panel.tabs.setEnabled(False)
        controller.refresh_character_menu()
        connect(
            models.characters.dataChanged,
            controller.refresh_character_menu,
        )
        panel.outline_plots.setPlotModel(
            models.plots,
            settings=self.settings,
        )
        panel.outline_plots.setShowSubPlot(True)
        self._character_delegate = outlineCharacterDelegate(
            models.characters,
            panel.characters,
        )
        panel.characters.setItemDelegate(self._character_delegate)
        self._step_delegate = plotDelegate(panel.steps)
        panel.steps.setItemDelegateForColumn(
            PlotStep.meta,
            self._step_delegate,
        )

    def unbind(self):
        self.controller.reset()
        if self._character_delegate is not None:
            self._character_delegate.mdlCharacter = None
        self._character_delegate = None
        self._step_delegate = None


class WorldProjectBinding:
    def __init__(self, controller):
        self.controller = controller
        self.panel = controller.panel

    @property
    def models(self):
        """The current project's models through the controller facade."""
        return self.controller.models

    def bind(self, connect):
        panel = self.panel
        models = self.models
        controller = self.controller
        panel.tree.setModel(models.world)
        for column in range(models.world.columnCount()):
            panel.tree.hideColumn(column)
        panel.tree.showColumn(0)
        controller.build_data_set_menu()
        for signal, slot in [
            (
                panel.tree.selectionModel().selectionChanged,
                controller.handle_selection_changed,
            ),
            (panel.add_item_button.clicked, controller.add_item),
            (
                panel.remove_item_button.clicked,
                controller.remove_selected_items,
            ),
        ]:
            connect(signal, slot, F.AUC)
        columns = (
            World.name,
            World.description,
            World.passion,
            World.conflict,
        )
        if len(panel.fields) != len(columns):
            raise ValueError("World panel field contract is incomplete.")
        for widget, column in zip(panel.fields, columns):
            widget.setModel(models.world)
            widget.setColumn(column)
        panel.tabs.setEnabled(False)
        panel.tree.expandAll()

    def unbind(self):
        self.controller.reset()


class ProjectFeatureBinding:
    """Composite lifecycle for independently bound project features."""

    def __init__(
        self,
        character_controller,
        plot_controller,
        world_controller,
        settings,
    ):
        self.bindings = (
            CharacterProjectBinding(character_controller),
            PlotProjectBinding(plot_controller, settings),
            WorldProjectBinding(world_controller),
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

    def dispose(self):
        self.unbind()
        for binding in self.bindings:
            binding.controller = None
            binding.panel = None
            if hasattr(binding, "settings"):
                binding.settings = None
        self.bindings = ()
