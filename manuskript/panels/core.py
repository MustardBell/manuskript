"""The panels Manuskript itself ships.

Declared here rather than inside the window so that any window can ask
the registry what core offers, the same way it asks about plugin panels.
Titles are source strings; the host translates them where it makes the
toggle, in the window's own context.
"""

from manuskript.panels.descriptor import (
    PER_WINDOW,
    PROJECT,
    SPLITTER_SLOT,
    PanelDescriptor,
    PanelState,
    SplitterSlot,
)


BOOK_SUMMARY = "core.book-summary"
PROJECT_TREE = "core.project-tree"
METADATA = "core.metadata"
STORYLINE = "core.storyline"

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


def core_panel_descriptors(plots_group, redaction_group, factories=None):
    """The four workspace panels, grouped under their main tabs.

    Slot indexes mirror where the Designer file has always put the
    widgets, so a factory-built copy lands exactly where the .ui one
    stood. ``factories`` maps panel ids to widget factories -- the Qt
    half, supplied by the ui layer so this module stays importable
    before a QApplication exists.
    """
    factories = factories or {}
    return (
        PanelDescriptor(
            id=BOOK_SUMMARY,
            title="Book summary",
            placement=SPLITTER_SLOT,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            slot=SplitterSlot("splitterPlot", 2),
            group=plots_group,
            default_visible=False,
            widget_factory=factories.get(BOOK_SUMMARY),
        ),
        PanelDescriptor(
            id=PROJECT_TREE,
            title="Project tree",
            placement=SPLITTER_SLOT,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            slot=SplitterSlot("splitterRedacH", 0),
            group=redaction_group,
            default_visible=True,
            widget_factory=factories.get(PROJECT_TREE),
        ),
        PanelDescriptor(
            id=METADATA,
            title="Metadata",
            placement=SPLITTER_SLOT,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            slot=SplitterSlot("splitterRedacH", 2),
            group=redaction_group,
            default_visible=False,
            widget_factory=factories.get(METADATA),
            state=METADATA_STATE,
        ),
        PanelDescriptor(
            id=STORYLINE,
            title="Story line",
            placement=SPLITTER_SLOT,
            scope=PROJECT,
            multiplicity=PER_WINDOW,
            slot=SplitterSlot("splitterRedacV", 1),
            group=redaction_group,
            default_visible=False,
            widget_factory=factories.get(STORYLINE),
        ),
    )


def register_core_panels(
        registry, plots_group, redaction_group, factories=None):
    """Idempotent: the registry is application scope, windows are not.

    The first window declares the core panels; every later window finds
    them already there.
    """
    for descriptor in core_panel_descriptors(
            plots_group, redaction_group, factories):
        if descriptor.id not in registry:
            registry.register(descriptor)
