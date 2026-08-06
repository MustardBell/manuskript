from manuskript.models.references import ReferenceNavigation


def reference_navigation_for(window, models):
    """Adapt one main window to the reference navigation interface.

    The window is what gets navigated -- tabs, lists, the editor. The
    models it navigates to are the project's, and are given rather than
    read off the window that happens to have them installed.
    """

    def open_character(character_id):
        item = window.lstCharacters.getItemByID(character_id)
        if item is None:
            return False
        window.tabMain.setCurrentIndex(window.TabPersos)
        window.lstCharacters.setCurrentItem(item)
        return True

    def open_text(text_id):
        index = models.outline.getIndexByID(text_id)
        if not index.isValid():
            return False
        window.tabMain.setCurrentIndex(window.TabRedac)
        window.mainEditor.setCurrentModelIndex(index, newTab=True)
        return True

    def open_plot(plot_id):
        item = window.lstPlots.getItemByID(plot_id)
        if item is None:
            return False
        window.tabMain.setCurrentIndex(window.TabPlots)
        window.lstPlots.setCurrentItem(item)
        return True

    def open_world(world_id):
        item = models.world.itemByID(world_id)
        if item is None:
            return False
        window.tabMain.setCurrentIndex(window.TabWorld)
        window.treeWorld.setCurrentIndex(
            models.world.indexFromItem(item)
        )
        return True

    return ReferenceNavigation(
        open_character=open_character,
        open_text=open_text,
        open_plot=open_plot,
        open_world=open_world,
    )
