"""Apply navigation history to one workspace's explicit views."""

from dataclasses import dataclass
from typing import Any

from PyQt5.QtCore import QModelIndex


@dataclass(frozen=True)
class NavigationTabs:
    """Tab positions used by semantic navigation targets."""

    characters: int
    plots: int
    world: int
    outline: int
    project: int


@dataclass(frozen=True)
class NavigationViews:
    """The only widgets history navigation is allowed to change."""

    tabs: Any
    tab_selector: Any
    characters: Any
    plots: Any
    world: Any
    outline: Any
    project_tree: Any
    back_action: Any
    forward_action: Any
    positions: NavigationTabs

    @classmethod
    def for_window(cls, window):
        """Translate a composed workspace into the navigation port."""
        return cls(
            tabs=window.tabMain,
            tab_selector=window.lstTabs,
            characters=window.lstCharacters,
            plots=window.lstPlots,
            world=window.treeWorld,
            outline=window.treeOutlineOutline,
            project_tree=window.corePanels.project_tree.tree,
            back_action=window.actBack,
            forward_action=window.actForward,
            positions=NavigationTabs(
                characters=window.TabPersos,
                plots=window.TabPlots,
                world=window.TabWorld,
                outline=window.TabOutline,
                project=window.TabRedac,
            ),
        )


class MainNavigationView:
    """Apply a history target without access to the rest of MainWindow."""

    def __init__(self, views, runtime):
        self.views = views
        # Models are resolved when navigation happens: another project can
        # replace the complete model set while these stable widgets remain.
        self._runtime = runtime
        self._handlers = {
            "character": self._navigate_character,
            "plot": self._navigate_plot,
            "world": self._navigate_world,
            "outline": self._navigate_outline,
            "redac": self._navigate_redaction,
            "main": self._navigate_main,
        }

    @property
    def _models(self):
        return self._runtime.models

    def navigate(self, entry):
        handler = self._handlers.get(entry[0])
        if handler is not None:
            handler(entry[1])

    def set_history_actions(self, *, can_go_back, can_go_forward):
        self.views.back_action.setEnabled(can_go_back)
        self.views.forward_action.setEnabled(can_go_forward)

    def _show_tab(self, index):
        if self.views.tabs.currentIndex() != index:
            self.views.tabs.setCurrentIndex(index)

    def _navigate_character(self, character_id):
        self._show_tab(self.views.positions.characters)
        characters = self.views.characters
        if character_id is None:
            characters.setCurrentItem(None)
            characters.clearSelection()
            return
        if characters.currentCharacterID() == character_id:
            return
        character = characters.getItemByID(character_id)
        if character is not None:
            characters.clearSelection()
            characters.setCurrentItem(character)

    def _navigate_plot(self, plot_id):
        self._show_tab(self.views.positions.plots)
        plots = self.views.plots
        if plot_id is None:
            plots.setCurrentItem(None)
            return
        if plots.currentPlotID() == plot_id:
            return
        plot = plots.getItemByID(plot_id)
        if plot is not None:
            plots.setCurrentItem(plot)

    def _navigate_world(self, world_id):
        self._show_tab(self.views.positions.world)
        tree = self.views.world
        selection = tree.selectionModel()
        if world_id is None:
            selection.clear()
            return
        current = (
            tree.currentIndex()
            if tree.selectedIndexes()
            else QModelIndex()
        )
        if (
            current.isValid()
            and self._models.world.ID(current) == world_id
        ):
            return
        target = self._models.world.indexByID(world_id)
        if target.isValid():
            tree.setCurrentIndex(target)

    def _navigate_outline(self, outline_id):
        self._show_tab(self.views.positions.outline)
        self._select_outline(self.views.outline, outline_id)

    def _navigate_redaction(self, outline_id):
        self._show_tab(self.views.positions.project)
        self._select_outline(self.views.project_tree, outline_id)

    def _select_outline(self, tree, outline_id):
        selection = tree.selectionModel()
        if outline_id is None:
            selection.clear()
            return
        current = selection.currentIndex()
        if (
            current.isValid()
            and self._models.outline.ID(current) == outline_id
        ):
            return
        outline = self._models.outline.getIndexByID(outline_id)
        if outline is not None:
            tree.setCurrentIndex(outline)

    def _navigate_main(self, tab_index):
        if self.views.tabs.currentIndex() != tab_index:
            self.views.tab_selector.setCurrentRow(tab_index)
