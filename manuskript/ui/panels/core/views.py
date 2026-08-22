"""Typed access to the core widgets a workspace window is built from.

Qt ``objectName`` values remain useful for saved layouts and UI inspection,
but they are not an application interface.  This module resolves those names
once, immediately after the core panels are built, and gives the rest of the
application a small, explicit view set instead of copying Designer-era widget
names onto :class:`MainWindow`.

Ten widgets, two owners. Three are tool panels and come from the window's
``PanelHost``; seven are the places a writer goes and come from its
``WorkspaceSurfaceHost``. Which of the ten is which is stated below as data
rather than spelled into the resolving code, because it is exactly what the
cutover changes -- and because a table can be asked whether it still agrees
with what each panel says it is, which ten hand-written lookups cannot.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from PyQt5.QtWidgets import (
    QPushButton,
    QWidget,
)

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
from manuskript.ui.panels.core.editor import EditorPanel
from manuskript.ui.panels.core.entities import (
    EntityBrowserPanel,
)
from manuskript.ui.panels.core.general import GeneralPanel
from manuskript.ui.panels.core.outline import OutlinePanel
from manuskript.ui.views.metadataView import metadataView
from manuskript.ui.views.storylineView import storylineView
from manuskript.ui.views.treeView import treeView


#: A tool panel, kept beside what is being written and owned by the
#: window's panel host.
TOOL_PANEL = "tool panel"

#: A place the writer goes, owned by the window's surface host.
SURFACE = "surface"

#: What to call the host each kind belongs to, when saying one was asked
#: and did not have it.
_HOST_NAMES = {TOOL_PANEL: "panel", SURFACE: "surface"}


def _panel_widget(host, panel_id, widget_type, owner=TOOL_PANEL):
    instance = host.instance(panel_id)
    if instance is None:
        # Naming the owner rather than only the id. With one host a miss
        # meant "not open yet"; with two it may equally mean "asked of the
        # wrong one", and those need different fixes.
        raise LookupError(
            "Required core {} {} is not open in this window's {} host."
            .format(owner, panel_id, _HOST_NAMES[owner])
        )
    widget = instance.widget
    if not isinstance(widget, widget_type):
        raise TypeError(
            "Core panel {} built {}, expected {}.".format(
                panel_id,
                type(widget).__name__,
                widget_type.__name__,
            )
        )
    return widget


def _required_child(parent, widget_type, object_name):
    child = parent.findChild(widget_type, object_name)
    if child is None:
        raise LookupError(
            "Core panel {} has no {} named {!r}.".format(
                parent.objectName(),
                widget_type.__name__,
                object_name,
            )
        )
    return child


@dataclass(frozen=True)
class ProjectTreePanelViews:
    """The project tree panel and its editing controls."""

    panel: QWidget
    tree: treeView
    add_folder: QPushButton
    add_text: QPushButton
    remove_item: QPushButton

    @classmethod
    def from_panel(cls, panel):
        return cls(
            panel=panel,
            tree=_required_child(panel, treeView, "treeRedacOutline"),
            add_folder=_required_child(
                panel, QPushButton, "btnRedacAddFolder",
            ),
            add_text=_required_child(panel, QPushButton, "btnRedacAddText"),
            remove_item=_required_child(
                panel, QPushButton, "btnRedacRemoveItem",
            ),
        )


@dataclass(frozen=True)
class CoreMember:
    """One core widget: what it is called, who owns it, what it must be.

    ``views`` is for the one member that is more than its widget -- the
    project tree, whose buttons are resolved alongside it.
    """

    attribute: str
    panel_id: str
    widget_type: type
    owner: str
    views: Optional[Callable[[Any], Any]] = None


#: The ten core widgets and which host each comes from.
#:
#: Said once, here. Seven of these move from the panel host to the surface
#: host in a single cutover, and a member left pointing at the old owner
#: would raise at window construction -- so a test asks the core registry
#: whether this still agrees with what each panel declares itself to be.
CORE_MEMBERS: Tuple[CoreMember, ...] = (
    CoreMember("general", GENERAL, GeneralPanel, SURFACE),
    CoreMember(
        "project_tree", PROJECT_TREE, QWidget, TOOL_PANEL,
        views=ProjectTreePanelViews.from_panel,
    ),
    CoreMember("metadata", METADATA, metadataView, TOOL_PANEL),
    CoreMember("storyline", STORYLINE, storylineView, TOOL_PANEL),
    CoreMember(
        "project_entities", PROJECT_ENTITIES, EntityBrowserPanel, SURFACE,
    ),
    CoreMember(
        "character_entities", CHARACTER_ENTITIES, EntityBrowserPanel,
        SURFACE,
    ),
    CoreMember("plot_entities", PLOT_ENTITIES, EntityBrowserPanel, SURFACE),
    CoreMember(
        "world_entities", WORLD_ENTITIES, EntityBrowserPanel, SURFACE,
    ),
    CoreMember("outline", OUTLINE, OutlinePanel, SURFACE),
    CoreMember("editor", EDITOR, EditorPanel, SURFACE),
)


@dataclass(frozen=True)
class CorePanelViewSet:
    """The core panel views belonging to one workspace window."""

    general: GeneralPanel
    project_tree: ProjectTreePanelViews
    metadata: metadataView
    storyline: storylineView
    project_entities: EntityBrowserPanel
    character_entities: EntityBrowserPanel
    plot_entities: EntityBrowserPanel
    world_entities: EntityBrowserPanel
    outline: OutlinePanel
    editor: EditorPanel

    @classmethod
    def from_hosts(cls, tools, surfaces):
        """Ask each owner for what it owns, and nothing else.

        ``tools`` and ``surfaces`` are the same object until the cutover:
        the panel host owns all ten today. Passing it twice is a true
        statement of that, and it means the cutover changes one argument
        at one call site rather than introducing this seam under pressure.
        """

        hosts = {TOOL_PANEL: tools, SURFACE: surfaces}
        resolved = {}
        for member in CORE_MEMBERS:
            widget = _panel_widget(
                hosts[member.owner],
                member.panel_id,
                member.widget_type,
                member.owner,
            )
            resolved[member.attribute] = (
                member.views(widget) if member.views else widget
            )
        return cls(**resolved)
