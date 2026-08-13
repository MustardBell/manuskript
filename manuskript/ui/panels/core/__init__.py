"""Widget factories for the panels Manuskript itself ships.

The declarations live Qt-free in :mod:`manuskript.panels.core`; this
package holds their Qt halves. A window passes these factories when it
registers the core panels, so the registry stays importable before any
QApplication exists.
"""

from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    EDITOR,
    GENERAL,
    METADATA,
    OUTLINE,
    PLOT_ENTITIES,
    PROJECT_ENTITIES,
    PROJECT_TREE,
    STORYLINE,
    WORLD_ENTITIES,
)
from manuskript.ui.panels.core.editor import build_editor
from manuskript.ui.panels.core.entities import (
    build_character_entities,
    build_plot_entities,
    build_project_entities,
    build_world_entities,
)
from manuskript.ui.panels.core.metadata import build_metadata
from manuskript.ui.panels.core.general import build_general
from manuskript.ui.panels.core.outline import build_outline
from manuskript.ui.panels.core.project_tree import build_project_tree
from manuskript.ui.panels.core.storyline import build_storyline
from manuskript.ui.panels.core.views import CorePanelViewSet


def core_panel_factories():
    """Panel id -> widget factory, one per core panel.

    Every project surface is factory-built; the Designer file owns only
    application chrome, welcome, and the opt-in debug page.
    """
    return {
        GENERAL: build_general,
        PROJECT_ENTITIES: build_project_entities,
        CHARACTER_ENTITIES: build_character_entities,
        PLOT_ENTITIES: build_plot_entities,
        WORLD_ENTITIES: build_world_entities,
        METADATA: build_metadata,
        PROJECT_TREE: build_project_tree,
        STORYLINE: build_storyline,
        OUTLINE: build_outline,
        EDITOR: build_editor,
    }


__all__ = ["CorePanelViewSet", "core_panel_factories"]
