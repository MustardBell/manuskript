"""The panels Manuskript itself ships.

Declared here rather than inside the window so that any window can ask
the registry what core offers, the same way it asks about plugin panels.
Titles are source strings; the host translates them where it makes the
toggle, in the window's own context.
"""

from manuskript.panels.descriptor import (
    DOCK,
    PER_WINDOW,
    PROJECT,
    PanelDescriptor,
    PanelState,
)


PROJECT_TREE = "core.project-tree"
METADATA = "core.metadata"
STORYLINE = "core.storyline"
PROJECT_ENTITIES = "core.entities.project"
CHARACTER_ENTITIES = "core.entities.characters"
PLOT_ENTITIES = "core.entities.plots"
WORLD_ENTITIES = "core.entities.world"
ENTITY_EDITOR = "core.entities.editor"

#: Where the metadata panel's revision list files its own arrangement.
#: Its own key rather than part of the panel's, because that is how it
#: has always been stored and saved layouts outlive this refactoring.
METADATA_REVISIONS_STATE = "core.metadata.revisions"

#: What the metadata panel remembers besides being shown: which of its
#: group boxes were collapsed, and how its revision list was arranged.
#: Said here, by the panel, rather than listed in the controller that
#: saves the window -- which had to name this panel's internals to do it.
METADATA_STATE = (
    PanelState(
        key=METADATA,
        capture=lambda panel: panel.saveState(),
        restore=lambda panel, value: panel.restoreState(value),
    ),
    PanelState(
        key=METADATA_REVISIONS_STATE,
        capture=lambda panel: panel.revisions.saveState(),
        restore=lambda panel, value: panel.revisions.restoreState(value),
    ),
)


def core_panel_descriptors(redaction_group, factories=None):
    """The workspace's movable core and canonical-entity panels.

    Only the redaction panels still answer to a main tab. The entity
    docks describe the whole project, so they claim no group and their
    toggles stay offered whichever tab is in front.
    """
    factories = factories or {}
    return (
        PanelDescriptor(
            id=PROJECT_TREE,
            title="Project tree",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            group=redaction_group,
            default_visible=True,
            widget_factory=factories.get(PROJECT_TREE),
        ),
        PanelDescriptor(
            id=METADATA,
            title="Metadata",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            group=redaction_group,
            default_visible=False,
            widget_factory=factories.get(METADATA),
            state=METADATA_STATE,
        ),
        PanelDescriptor(
            id=STORYLINE,
            title="Story line",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            group=redaction_group,
            default_visible=False,
            widget_factory=factories.get(STORYLINE),
        ),
        PanelDescriptor(
            id=PROJECT_ENTITIES,
            title="Project",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=False,
            widget_factory=factories.get(PROJECT_ENTITIES),
        ),
        PanelDescriptor(
            id=CHARACTER_ENTITIES,
            title="Characters",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=True,
            widget_factory=factories.get(CHARACTER_ENTITIES),
        ),
        PanelDescriptor(
            id=PLOT_ENTITIES,
            title="Plots",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=False,
            widget_factory=factories.get(PLOT_ENTITIES),
        ),
        PanelDescriptor(
            id=WORLD_ENTITIES,
            title="World & entities",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=False,
            widget_factory=factories.get(WORLD_ENTITIES),
        ),
        PanelDescriptor(
            id=ENTITY_EDITOR,
            title="Entity editor",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=True,
            widget_factory=factories.get(ENTITY_EDITOR),
        ),
    )


def register_core_panels(registry, redaction_group, factories=None):
    """Idempotent: the registry is application scope, windows are not.

    The first window declares the core panels; every later window finds
    them already there.
    """
    for descriptor in core_panel_descriptors(redaction_group, factories):
        if descriptor.id not in registry:
            registry.register(descriptor)
