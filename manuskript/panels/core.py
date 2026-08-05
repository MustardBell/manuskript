"""The panels Manuskript itself ships.

Declared here rather than inside the window so that any window can ask
the registry what core offers, the same way it asks about plugin panels.
Titles are source strings; the host translates them where it makes the
toggle, in the window's own context.
"""

from manuskript.panels.descriptor import (
    SPLITTER_SLOT,
    PanelDescriptor,
    SplitterSlot,
)


BOOK_SUMMARY = "core.book-summary"
PROJECT_TREE = "core.project-tree"
METADATA = "core.metadata"
STORYLINE = "core.storyline"


def core_panel_descriptors(plots_group, redaction_group):
    """The four workspace panels, grouped under their main tabs.

    Slot indexes mirror where the Designer file has always put the
    widgets, so a factory-built copy lands exactly where the .ui one
    stood.
    """
    return (
        PanelDescriptor(
            id=BOOK_SUMMARY,
            title="Book summary",
            placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterPlot", 2),
            group=plots_group,
            default_visible=False,
        ),
        PanelDescriptor(
            id=PROJECT_TREE,
            title="Project tree",
            placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterRedacH", 0),
            group=redaction_group,
            default_visible=True,
        ),
        PanelDescriptor(
            id=METADATA,
            title="Metadata",
            placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterRedacH", 2),
            group=redaction_group,
            default_visible=False,
        ),
        PanelDescriptor(
            id=STORYLINE,
            title="Story line",
            placement=SPLITTER_SLOT,
            slot=SplitterSlot("splitterRedacV", 1),
            group=redaction_group,
            default_visible=False,
        ),
    )


def register_core_panels(registry, plots_group, redaction_group):
    """Idempotent: the registry is application scope, windows are not.

    The first window declares the core panels; every later window finds
    them already there.
    """
    for descriptor in core_panel_descriptors(
            plots_group, redaction_group):
        if descriptor.id not in registry:
            registry.register(descriptor)
