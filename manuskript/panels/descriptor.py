"""What a side panel is, said without Qt.

A panel is anything the workspace shows beside the document: the project
tree, the metadata editor, a plugin's notes. Naming them all in one
vocabulary is what lets one host build any of them for any window, and
later move one between windows by handing over its instance instead of
rewiring signals.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional


#: The panel sits inside a named splitter, at a fixed position.
SPLITTER_SLOT = "splitter-slot"

#: The panel lives in a dock area around the document.
DOCK = "dock"

PLACEMENTS = (SPLITTER_SLOT, DOCK)


@dataclass(frozen=True)
class SplitterSlot:
    """Where a splitter panel goes: which splitter, and which position."""

    splitter: str
    index: int


@dataclass(frozen=True)
class PanelDescriptor:
    """One panel, by name, before any widget of it exists.

    ``widget_factory(context, parent)`` builds the panel's widget and is
    what makes a second window able to have its own copy. It may be None
    only while a panel is transitional -- still built somewhere else and
    merely attached to its host. That is a state to migrate away from,
    not to design against.

    ``group`` identifies the main tab whose toolbar offers the toggle,
    for panels that only make sense beside one view. Dock panels leave
    it None and are offered everywhere.
    """

    id: str
    title: str
    placement: str = DOCK
    slot: Optional[SplitterSlot] = None
    group: Optional[Any] = None
    default_visible: bool = True
    requires_project: bool = False
    #: The Qt objectName for the panel's container. Saved window layouts
    #: identify docks by this, so it stays what it always was even where
    #: the panel id could not (plugin docks predate panel ids).
    object_name: str = ""
    widget_factory: Optional[Callable[..., Any]] = None

    def __post_init__(self):
        if not self.id or "." not in self.id:
            raise ValueError(
                "Panel IDs are dotted names like 'core.metadata': "
                "got {!r}.".format(self.id)
            )
        if not self.title:
            raise ValueError(
                "Panel {} needs a title.".format(self.id)
            )
        if self.placement not in PLACEMENTS:
            raise ValueError(
                "Panel {} has placement {!r}; it must be one of {}."
                .format(self.id, self.placement, ", ".join(PLACEMENTS))
            )
        if self.placement == SPLITTER_SLOT and self.slot is None:
            raise ValueError(
                "Panel {} sits in a splitter, so it has to say which "
                "slot.".format(self.id)
            )
