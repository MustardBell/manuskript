from manuskript.models.references import ReferenceNavigation
from manuskript.panels.core import EDITOR


def reference_navigation_for(window, models, open_entity=None):
    """Adapt one main window to the reference navigation interface.

    The window is what gets navigated -- tabs, lists, the editor. The
    models it navigates to are the project's, and are given rather than
    read off the window that happens to have them installed.
    """

    def open_character(character_id):
        if open_entity is None:
            return False
        return bool(
            open_entity(character_id)
            or open_entity("legacy:character:{}".format(character_id))
        )

    def open_text(text_id):
        index = models.outline.getIndexByID(text_id)
        if not index.isValid():
            return False
        window.activatePanel(EDITOR)
        window.corePanels.editor.editor.setCurrentModelIndex(
            index, newTab=True
        )
        return True

    def open_plot(plot_id):
        if open_entity is None:
            return False
        return bool(
            open_entity(plot_id)
            or open_entity("legacy:plot:{}".format(plot_id))
        )

    def open_world(world_id):
        if open_entity is None:
            return False
        return bool(
            open_entity(world_id)
            or open_entity("legacy:world:{}".format(world_id))
        )

    return ReferenceNavigation(
        open_character=open_character,
        open_text=open_text,
        open_plot=open_plot,
        open_world=open_world,
        open_entity=open_entity,
    )
