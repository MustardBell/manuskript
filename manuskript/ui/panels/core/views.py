"""Typed access to the core panel widgets owned by one panel host.

Qt ``objectName`` values remain useful for saved layouts and UI inspection,
but they are not an application interface.  This module resolves those names
once, immediately after the core panels are built, and gives the rest of the
application a small, explicit view set instead of copying Designer-era widget
names onto :class:`MainWindow`.
"""

from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QPushButton,
    QWidget,
)

from manuskript.panels.core import (
    CHARACTER_ENTITIES,
    ENTITY_EDITOR,
    METADATA,
    PLOT_ENTITIES,
    PROJECT_ENTITIES,
    PROJECT_TREE,
    STORYLINE,
    WORLD_ENTITIES,
)
from manuskript.ui.panels.core.entities import (
    EntityBrowserPanel,
    EntityEditorPanel,
)
from manuskript.ui.views.metadataView import metadataView
from manuskript.ui.views.storylineView import storylineView
from manuskript.ui.views.treeView import treeView


def _panel_widget(host, panel_id, widget_type):
    instance = host.instance(panel_id)
    if instance is None:
        raise LookupError("Required core panel {} is not open.".format(panel_id))
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
class CorePanelViewSet:
    """The core panel views belonging to one workspace window."""

    project_tree: ProjectTreePanelViews
    metadata: metadataView
    storyline: storylineView
    project_entities: EntityBrowserPanel
    character_entities: EntityBrowserPanel
    plot_entities: EntityBrowserPanel
    world_entities: EntityBrowserPanel
    entity_editor: EntityEditorPanel

    @classmethod
    def from_host(cls, host):
        project_tree = _panel_widget(host, PROJECT_TREE, QWidget)
        return cls(
            project_tree=ProjectTreePanelViews.from_panel(project_tree),
            metadata=_panel_widget(host, METADATA, metadataView),
            storyline=_panel_widget(host, STORYLINE, storylineView),
            project_entities=_panel_widget(
                host, PROJECT_ENTITIES, EntityBrowserPanel
            ),
            character_entities=_panel_widget(
                host, CHARACTER_ENTITIES, EntityBrowserPanel
            ),
            plot_entities=_panel_widget(
                host, PLOT_ENTITIES, EntityBrowserPanel
            ),
            world_entities=_panel_widget(
                host, WORLD_ENTITIES, EntityBrowserPanel
            ),
            entity_editor=_panel_widget(
                host, ENTITY_EDITOR, EntityEditorPanel
            ),
        )
