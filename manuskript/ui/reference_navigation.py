from manuskript.models.references import ReferenceNavigation


def reference_navigation_for(window):
    """Adapt one main window to the reference navigation interface."""

    def open_character(character_id):
        item = window.lstCharacters.getItemByID(character_id)
        if item is None:
            return False
        window.tabMain.setCurrentIndex(window.TabPersos)
        window.lstCharacters.setCurrentItem(item)
        return True

    def open_text(text_id):
        index = window.mdlOutline.getIndexByID(text_id)
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
        item = window.mdlWorld.itemByID(world_id)
        if item is None:
            return False
        window.tabMain.setCurrentIndex(window.TabWorld)
        window.treeWorld.setCurrentIndex(window.mdlWorld.indexFromItem(item))
        return True

    return ReferenceNavigation(
        open_character=open_character,
        open_text=open_text,
        open_plot=open_plot,
        open_world=open_world,
    )
