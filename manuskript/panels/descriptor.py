"""What a workspace shows, said without Qt, in two kinds.

There are two of them and they were one for too long.

A **workspace surface** is a place the writer goes: the manuscript, the
cast, the outline, the editor. It is what the navigator lists. It lives in
the window's central host, it is not a dock, and it may be docked without
that being what it is -- the user's rule, and the correction that produced
this split: *"anything that navigation has is NOT a dock. It could be
docked but anything that navigation has and can enable is a window."*

A **tool panel** is something kept beside what is being written: the
project tree, the metadata editor, a plugin's notes. It lives in a dock,
it may float into a utility window, and that is the whole of what it is.

They were one type with a `navigator` field bolted on, which made
contradictions expressible -- a navigator row with a splitter slot, a dock
placement on a place the writer goes -- and left every consumer to
remember which fields meant anything for which kind. The fields have
different domains, so the types do.

One registry still holds both, because there is one id namespace and one
place to ask what exists. It answers `surfaces()` and `tool_panels()`
separately, since almost nothing wants both.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple


@dataclass(frozen=True)
class NavigatorEntry:
    """A panel's row in the window's navigator.

    The navigator lists the places a person goes -- the manuscript, the
    cast, the world -- rather than every panel that exists. A panel says
    it belongs there and what to draw; the window decides nothing about
    which panels it has heard of, so a plugin's panel can take a row on
    the same terms as a core one.

    ``icon`` is a theme icon name, resolved where icons are resolved.
    ``order`` sorts the rows; core leaves gaps so anything else can land
    between them without renumbering.
    """

    label: str
    icon: str = ""
    order: int = 1000


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
class ToolPanelDescriptor:
    """One tool panel, by name, before any widget of it exists.

    ``widget_factory(context, parent)`` builds the panel's widget and is
    what makes a second window able to have its own copy. It may be None
    only while a panel is transitional -- still built somewhere else and
    merely attached to its host. That is a state to migrate away from,
    not to design against.

    ``group`` is retained for compatibility with older extensions that
    grouped toggles around a central tab. Independent docks leave it None
    and are offered everywhere.

    A tool panel has no navigator row, and no field for one. It briefly had
    one that only accepted None, so that a refusal could explain itself --
    which is a contradiction kept in the type to improve an error message.
    Asking for a navigator row is asking to be a place the writer goes, and
    that is ``WorkspaceSurfaceDescriptor``.

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
    #: Surface ids where this panel is part of the default working scene.
    #: None means independent visibility: changing surfaces does not touch
    #: it.  A tuple opts into routing, and may be empty for a panel hidden by
    #: default on every surface but still remembered independently per one.
    visible_with_surfaces: Optional[Tuple[str, ...]] = None
    #: Preferred width when a routed dock first joins a left/right scene.
    #: Zero leaves sizing to Qt. It is a default, not a minimum; later sizes
    #: are remembered by the routing controller.
    preferred_extent: int = 0
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
        if self.visible_with_surfaces is not None:
            surfaces = tuple(self.visible_with_surfaces)
            if any(
                not isinstance(surface_id, str)
                or "." not in surface_id
                for surface_id in surfaces
            ):
                raise ValueError(
                    "Panel {} surface routes must be dotted surface ids."
                    .format(self.id)
                )
            if len(surfaces) != len(set(surfaces)):
                raise ValueError(
                    "Panel {} names a surface route twice.".format(self.id)
                )
            object.__setattr__(self, "visible_with_surfaces", surfaces)
        try:
            preferred_extent = int(self.preferred_extent)
        except (TypeError, ValueError):
            raise ValueError(
                "Panel {} preferred extent must be a non-negative integer."
                .format(self.id)
            ) from None
        if preferred_extent < 0:
            raise ValueError(
                "Panel {} preferred extent must be a non-negative integer."
                .format(self.id)
            )
        object.__setattr__(self, "preferred_extent", preferred_extent)

    @property
    def requires_project(self):
        """Whether this panel can only be shown with a project open."""
        return self.scope == PROJECT

    @property
    def per_window(self):
        """Whether each window builds its own, rather than sharing one."""
        return self.multiplicity == PER_WINDOW


@dataclass(frozen=True)
class WorkspaceSurfaceDescriptor:
    """One place the writer goes, before any widget of it exists.

    A surface is hosted by the window's central surface host, and moving one
    between windows changes which workspace owns it rather than where it is
    docked. So it has no ``placement`` to choose, no splitter ``slot`` and no
    ``group``: those are a tool panel's vocabulary and mean nothing here.

    ``multiplicity`` says at most one presentation of this surface **may**
    belong to a workspace. It does not say every workspace gets one -- that
    reading is what made a second window construct its own Editor and left
    nothing for a move to hand over. Which surfaces a particular workspace
    holds is the workspace's state, not this description.

    There is deliberately no ``placement``. A surface briefly answered
    ``DOCK`` from a property so the existing host could mount it, which let
    every old consumer go on believing everything has a placement. The
    temporary wrongness belongs in the host that is about to lose it, where
    it is one conspicuous branch to delete, rather than in the description
    of what a surface is.
    """

    id: str
    title: str
    scope: str = PROJECT
    multiplicity: str = PER_WINDOW
    #: The Qt objectName a saved layout files this by. Kept while surfaces
    #: are still hosted in docks; it is layout identity rather than
    #: placement, and outlives the container it currently names.
    object_name: str = ""
    widget_factory: Optional[Callable[..., Any]] = None
    state: Tuple[PanelState, ...] = ()
    #: Where this sits in the navigator. Optional: a surface may exist
    #: without being listed, but anything listed is a surface.
    navigator: Optional["NavigatorEntry"] = None

    # There is no default_visible. A surface is not shown or hidden: one
    # of them is what the workspace is currently showing and the rest are
    # simply not that one. It had the field while surfaces were docks,
    # where three of the seven claimed to be visible at once.

    def __post_init__(self):
        if not self.id or "." not in self.id:
            raise ValueError(
                "Surface IDs are dotted names like 'core.editor': "
                "got {!r}.".format(self.id)
            )
        if not self.title:
            raise ValueError("Surface {} needs a title.".format(self.id))
        if self.scope not in SCOPES:
            raise ValueError(
                "Surface {} has scope {!r}; it must be one of {}."
                .format(self.id, self.scope, ", ".join(SCOPES))
            )
        if self.multiplicity not in MULTIPLICITIES:
            raise ValueError(
                "Surface {} has multiplicity {!r}; it must be one of {}."
                .format(self.id, self.multiplicity, ", ".join(MULTIPLICITIES))
            )

    @property
    def requires_project(self):
        return self.scope == PROJECT

    @property
    def per_window(self):
        return self.multiplicity == PER_WINDOW


#: Either kind, for the few places that genuinely hold both while surfaces
#: are still mounted by the panel host. Deliberately not called
#: ``PanelDescriptor``: that name meant "tool panel" for years, and reusing
#: it for the union would make every annotation ambiguous again.
WorkspaceItemDescriptor = (ToolPanelDescriptor, WorkspaceSurfaceDescriptor)


def group_of(descriptor):
    """The toggle group a tool panel belongs to, or None for a surface.

    Asked here rather than with ``getattr``: reaching for a field and
    accepting its absence is how a reader ends up inferring what kind of
    thing they are holding, which is the habit the two types exist to end.
    A surface has no group because it is not a toggle in a group -- it is a
    place the writer goes.
    """

    if isinstance(descriptor, ToolPanelDescriptor):
        return descriptor.group
    return None
