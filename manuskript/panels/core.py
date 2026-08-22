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
    NavigatorEntry,
    PanelState,
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)


PROJECT_TREE = "core.project-tree"
METADATA = "core.metadata"
STORYLINE = "core.storyline"
GENERAL = "core.general"
OUTLINE = "core.outline"
EDITOR = "core.editor"
PROJECT_ENTITIES = "core.entities.project"
CHARACTER_ENTITIES = "core.entities.characters"
PLOT_ENTITIES = "core.entities.plots"
WORLD_ENTITIES = "core.entities.world"

CORE_SURFACE_IDS = (
    GENERAL,
    PROJECT_ENTITIES,
    CHARACTER_ENTITIES,
    PLOT_ENTITIES,
    WORLD_ENTITIES,
    OUTLINE,
    EDITOR,
)

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


def core_panel_descriptors(redaction_group=None, factories=None):
    """The workspace's movable core and canonical-entity panels.

    ``redaction_group`` is accepted while third-party callers migrate from
    the old tab-grouped API.  It is intentionally ignored: core surfaces are
    independently movable now, so no main tab owns their visibility toggle.
    """
    factories = factories or {}
    return (
        WorkspaceSurfaceDescriptor(
            id=GENERAL,
            title="General",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(GENERAL),
            navigator=NavigatorEntry(
                label="General", icon="general", order=100,
            ),
        ),
        ToolPanelDescriptor(
            id=PROJECT_TREE,
            title="Project tree",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=True,
            widget_factory=factories.get(PROJECT_TREE),
        ),
        ToolPanelDescriptor(
            id=METADATA,
            title="Metadata",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=False,
            widget_factory=factories.get(METADATA),
            state=METADATA_STATE,
        ),
        ToolPanelDescriptor(
            id=STORYLINE,
            title="Story line",
            placement=DOCK,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            default_visible=False,
            widget_factory=factories.get(STORYLINE),
        ),
        WorkspaceSurfaceDescriptor(
            id=PROJECT_ENTITIES,
            title="Project",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(PROJECT_ENTITIES),
            navigator=NavigatorEntry(
                label="Summary", icon="summary", order=200,
            ),
        ),
        WorkspaceSurfaceDescriptor(
            id=CHARACTER_ENTITIES,
            title="Characters",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(CHARACTER_ENTITIES),
            navigator=NavigatorEntry(
                label="Characters", icon="characters", order=300,
            ),
        ),
        WorkspaceSurfaceDescriptor(
            id=PLOT_ENTITIES,
            title="Plots",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(PLOT_ENTITIES),
            navigator=NavigatorEntry(
                label="Plots", icon="plots", order=400,
            ),
        ),
        WorkspaceSurfaceDescriptor(
            id=WORLD_ENTITIES,
            title="World & entities",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(WORLD_ENTITIES),
            navigator=NavigatorEntry(
                label="World", icon="world", order=500,
            ),
        ),
        WorkspaceSurfaceDescriptor(
            id=OUTLINE,
            title="Outline",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(OUTLINE),
            navigator=NavigatorEntry(
                label="Outline", icon="outline", order=600,
            ),
        ),
        WorkspaceSurfaceDescriptor(
            id=EDITOR,
            title="Editor",
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            widget_factory=factories.get(EDITOR),
            navigator=NavigatorEntry(
                label="Editor", icon="editor", order=700,
            ),
        ),
    )


def register_core_panels(registry, redaction_group=None, factories=None):
    """Idempotent: the registry is application scope, windows are not.

    The first window declares the core panels; every later window finds
    them already there.
    """
    for descriptor in core_panel_descriptors(redaction_group, factories):
        if descriptor.id not in registry:
            registry.register(descriptor)
