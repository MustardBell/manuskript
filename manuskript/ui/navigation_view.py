class MainNavigationView:
    """Apply a history target to concrete main-window widgets."""

    def __init__(self, window, runtime):
        self.window = window
        # The window is what gets navigated; the models navigated to
        # belong to the project. Read from the runtime when needed,
        # because this view is built before any project is open.
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
        self.window.actBack.setEnabled(can_go_back)
        self.window.actForward.setEnabled(can_go_forward)

    def _show_tab(self, index):
        if self.window.tabMain.currentIndex() != index:
            self.window.tabMain.setCurrentIndex(index)

    def _navigate_character(self, character_id):
        self._show_tab(self.window.TabPersos)
        characters = self.window.lstCharacters
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
        self._show_tab(self.window.TabPlots)
        plots = self.window.lstPlots
        if plot_id is None:
            plots.setCurrentItem(None)
            return
        if plots.currentPlotID() == plot_id:
            return
        plot = plots.getItemByID(plot_id)
        if plot is not None:
            plots.setCurrentItem(plot)

    def _navigate_world(self, world_id):
        self._show_tab(self.window.TabWorld)
        if world_id is None:
            self.window.treeWorld.selectionModel().clear()
            return
        index = self.window.worldController.current_index()
        if (
            not index.isValid()
            or self._models.world.ID(index) != world_id
        ):
            self.window.worldController.select_by_id(world_id)

    def _navigate_outline(self, outline_id):
        self._show_tab(self.window.TabOutline)
        self._select_outline(self.window.treeOutlineOutline, outline_id)

    def _navigate_redaction(self, outline_id):
        self._show_tab(self.window.TabRedac)
        self._select_outline(
            self.window.corePanels.project_tree.tree,
            outline_id,
        )

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
        if self.window.tabMain.currentIndex() != tab_index:
            self.window.lstTabs.setCurrentRow(tab_index)
