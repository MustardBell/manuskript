"""What a side panel is, said without Qt.

A panel is anything the workspace shows beside the document: the project
tree, the metadata editor, a plugin's notes. Naming them all in one
vocabulary is what lets one host build any of them for any window, and
later move one between windows by handing over its instance instead of
rewiring signals.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple


#: The panel sits inside a named splitter, at a fixed position.
SPLITTER_SLOT = "splitter-slot"

#: The panel lives in a dock area around the document.
DOCK = "dock"

PLACEMENTS = (SPLITTER_SLOT, DOCK)


# --------------------------------------------------------------- scope
# What a panel's content belongs to, which is what decides when it can
# be shown and when it has to be put away.

#: Meaningful whenever the application is running.
APPLICATION = "application"

#: Meaningful only while a project is open, and closed with it.
PROJECT = "project"

SCOPES = (APPLICATION, PROJECT)


# -------------------------------------------------------- multiplicity
# How many of a panel may exist at once. This is the rule that decides
# whether two windows share one panel or get one each, and getting it
# wrong is what made opening a second window fail: a per-window panel
# was being declared as though it were a singleton.

#: One in the whole application. A second window cannot have its own;
#: it can only be given the one that exists.
SINGLETON = "singleton"

#: One per window, built from the same description. Every window may
#: show it, and each window's is its own.
PER_WINDOW = "per-window"

MULTIPLICITIES = (SINGLETON, PER_WINDOW)


@dataclass(frozen=True)
class SplitterSlot:
    """Where a splitter panel goes: which splitter, and which position."""

    splitter: str
    index: int


@dataclass(frozen=True)
class PanelState:
    """One thing a panel remembers between sessions, and how.

    Beyond being shown or hidden, some panels have an arrangement of their
    own -- which of the metadata panel's group boxes were collapsed, which
    columns its revision list showed. The controller that saves a window's
    layout used to hold that list itself, together with the widget methods
    to call and the widget to call them on, so a new panel with state to
    keep meant editing the central controller and naming that panel's
    internals in it.

    A panel says what it remembers instead. ``capture(widget)`` answers
    with something a settings file can hold; ``restore(widget, value)``
    takes it back. ``key`` is what that value is filed under and is part of
    the stored format, so it outlives renamings of everything else.
    """

    key: str
    capture: Callable[[Any], Any]
    restore: Callable[[Any, Any], None]

    def __post_init__(self):
        if not self.key:
            raise ValueError("Remembered panel state needs a key.")
        if not callable(self.capture) or not callable(self.restore):
            raise ValueError(
                "Panel state {} needs both a capture and a restore."
                .format(self.key)
            )


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

    ``scope`` and ``multiplicity`` say what a panel belongs to and how
    many of it there may be. They are stated rather than inferred
    because the alternative was every host deciding for itself, and two
    hosts deciding differently is what made a second window fail to
    open at all.
    """

    id: str
    title: str
    placement: str = DOCK
    slot: Optional[SplitterSlot] = None
    group: Optional[Any] = None
    default_visible: bool = True
    scope: str = APPLICATION
    multiplicity: str = PER_WINDOW
    #: The Qt objectName for the panel's container. Saved window layouts
    #: identify docks by this, so it stays what it always was even where
    #: the panel id could not (plugin docks predate panel ids).
    object_name: str = ""
    widget_factory: Optional[Callable[..., Any]] = None
    #: What this panel remembers between sessions, beyond whether it was
    #: showing. Empty for the panels whose whole state is their visibility.
    state: Tuple[PanelState, ...] = ()

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
        if self.scope not in SCOPES:
            raise ValueError(
                "Panel {} has scope {!r}; it must be one of {}."
                .format(self.id, self.scope, ", ".join(SCOPES))
            )
        if self.multiplicity not in MULTIPLICITIES:
            raise ValueError(
                "Panel {} has multiplicity {!r}; it must be one of {}."
                .format(
                    self.id,
                    self.multiplicity,
                    ", ".join(MULTIPLICITIES),
                )
            )

    @property
    def requires_project(self):
        """Whether this panel can only be shown with a project open."""
        return self.scope == PROJECT

    @property
    def per_window(self):
        """Whether each window builds its own, rather than sharing one."""
        return self.multiplicity == PER_WINDOW
