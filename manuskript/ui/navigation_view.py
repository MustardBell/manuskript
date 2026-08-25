"""Apply semantic navigation history to one workspace's panel surfaces."""

from dataclasses import dataclass
from typing import Any, Callable

from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    EDITOR,
    OUTLINE,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
)


@dataclass(frozen=True)
class NavigationViews:
    """The only capabilities history navigation may change."""

    activate_panel: Callable[[str], bool]
    surface_widget: Callable[[str], Any]
    outline_selection: Any
    back_action: Any
    forward_action: Any

    @classmethod
    def for_window(cls, window):
        core = window.corePanels

        def surface_widget(surface_id):
            instance = window.surfaceHost.instance(surface_id)
            return instance.widget if instance is not None else None

        return cls(
            activate_panel=window.activatePanel,
            surface_widget=surface_widget,
            outline_selection=window.outlineSelection,
            back_action=window.actBack,
            forward_action=window.actForward,
        )


class MainNavigationView:
    """Resolve history entries through stable panel ids, never tab indexes."""

    _ENTITY_PANELS = {
        "character": CHARACTER_ENTITIES,
        "plot": PLOT_ENTITIES,
        "world": WORLD_ENTITIES,
    }

    def __init__(self, views, runtime):
        self.views = views
        self._runtime = runtime
        self._handlers = {
            "character": self._navigate_entity,
            "plot": self._navigate_entity,
            "world": self._navigate_entity,
            "outline": self._navigate_outline,
            "redac": self._navigate_redaction,
            "panel": self._navigate_panel,
        }

    @property
    def _models(self):
        return self._runtime.models

    def navigate(self, entry):
        handler = self._handlers.get(entry[0])
        if handler is None:
            return
        if entry[0] in self._ENTITY_PANELS:
            handler(entry[0], entry[1])
        else:
            handler(entry[1])

    def set_history_actions(self, *, can_go_back, can_go_forward):
        self.views.back_action.setEnabled(can_go_back)
        self.views.forward_action.setEnabled(can_go_forward)

    def _navigate_entity(self, kind, entity_id):
        surface_id = self._ENTITY_PANELS[kind]
        if not self.views.activate_panel(surface_id):
            return
        panel = self.views.surface_widget(surface_id)
        if panel is None:
            return
        if entity_id is None:
            panel.tree.clearSelection()
            panel.tree.setCurrentItem(None)
            return
        candidates = (str(entity_id), "legacy:{}:{}".format(kind, entity_id))
        for candidate in candidates:
            if panel.select_entity(candidate):
                break

    def _navigate_outline(self, outline_id):
        if not self.views.activate_panel(OUTLINE):
            return
        panel = self.views.surface_widget(OUTLINE)
        if panel is not None:
            self._select_outline(panel.treeOutlineOutline, outline_id)

    def _navigate_redaction(self, outline_id):
        self.views.activate_panel(EDITOR)
        self._select_outline(self.views.outline_selection, outline_id)

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

    def _navigate_panel(self, panel_id):
        self.views.activate_panel(panel_id)
