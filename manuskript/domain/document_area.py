"""How the document area is arranged, said without Qt.

The editor could always split, but only ever down one side. Each area
held a tab group and optionally *one* neighbour, which held a tab group
and optionally one neighbour, and so on:

    tabs | tabs | tabs | tabs

That is a comb, not a tree. There was no way to say "split the left half
in two and leave the right half alone", because the left half was always
a bare tab group by construction::

              split
             /     \\
         split      split
        /    \\     /    \\
      tabs  tabs tabs  tabs

This module says what an arrangement *is*, so that the shape is a fact
about the model rather than a consequence of how widgets happen to nest.
A node is either a tab group -- documents open side by side -- or a split
of two nodes, either of which may itself be a split.

Nothing here is a widget. The arrangement can be read, written, compared
and migrated with no application running, which is what lets the old
comb format be converted without guessing.
"""

from dataclasses import dataclass, field
from typing import Any, Tuple, Union


#: Side by side.
HORIZONTAL = "horizontal"

#: One above the other.
VERTICAL = "vertical"

ORIENTATIONS = (HORIZONTAL, VERTICAL)


@dataclass(frozen=True)
class TabGroup:
    """Documents open in one place, as tabs.

    A leaf. ``current`` is which of them is on top, and is clamped when
    read rather than trusted, because a stored arrangement can outlive
    the documents it names.
    """

    documents: Tuple[str, ...] = ()
    current: int = 0

    def __post_init__(self):
        # An empty tab has no document, and an id read off one comes back
        # as None. Keeping it would record a document called "None" and
        # try to reopen it on the next launch.
        object.__setattr__(
            self,
            "documents",
            tuple(
                str(one)
                for one in self.documents
                if one is not None and str(one) not in ("", "None")
            ),
        )

    @property
    def current_document(self):
        if not self.documents:
            return None
        index = min(max(self.current, 0), len(self.documents) - 1)
        return self.documents[index]

    def all_documents(self):
        return self.documents

    def groups(self):
        return (self,)


@dataclass(frozen=True)
class Split:
    """Two areas, either of which may itself be split.

    ``sizes`` is how the space was divided, kept as it was found and
    applied only when it still describes the same number of parts.
    """

    orientation: str
    first: "DocumentAreaNode"
    second: "DocumentAreaNode"
    sizes: Tuple[int, ...] = ()

    def __post_init__(self):
        if self.orientation not in ORIENTATIONS:
            raise ValueError(
                "A split is {}; got {!r}.".format(
                    " or ".join(ORIENTATIONS), self.orientation,
                )
            )
        object.__setattr__(self, "sizes", tuple(self.sizes))

    def all_documents(self):
        return self.first.all_documents() + self.second.all_documents()

    def groups(self):
        return self.first.groups() + self.second.groups()


DocumentAreaNode = Union[TabGroup, Split]


# --------------------------------------------------------- the comb

#: What the old format called an unsplit area.
LEGACY_UNSPLIT = 0

#: The old split states, in the orientation each meant.
LEGACY_ORIENTATIONS = {
    1: HORIZONTAL,
    2: VERTICAL,
}


def from_legacy(stored):
    """One old ``[state, ids, neighbour]`` triple as a node.

    The old format could only describe a comb, so this never has to
    invent a shape -- every triple maps to exactly one node.
    """
    if not stored:
        return TabGroup()
    state = stored[0] if len(stored) > 0 else LEGACY_UNSPLIT
    documents = stored[1] if len(stored) > 1 and stored[1] else ()
    neighbour = stored[2] if len(stored) > 2 else None
    group = TabGroup(documents=documents)
    orientation = LEGACY_ORIENTATIONS.get(state)
    if orientation is None or not neighbour:
        # Split with nothing beside it was a split in name only.
        return group
    return Split(
        orientation=orientation,
        first=group,
        second=from_legacy(neighbour),
    )


def is_comb(node):
    """Whether this arrangement is one the old format could express.

    True when every split's first side is a bare tab group -- which is
    every arrangement the editor could previously make.
    """
    if isinstance(node, TabGroup):
        return True
    return isinstance(node.first, TabGroup) and is_comb(node.second)


# ------------------------------------------------------ serialisation

def to_data(node):
    """A plain structure, for storing."""
    if isinstance(node, TabGroup):
        return {
            "tabs": list(node.documents),
            "current": node.current,
        }
    return {
        "split": node.orientation,
        "first": to_data(node.first),
        "second": to_data(node.second),
        "sizes": list(node.sizes),
    }


def from_data(stored):
    """A stored structure as a node, or None when unreadable.

    Unreadable rather than raising: an arrangement is a convenience, and
    losing it must not stop somebody opening their project.
    """
    if not isinstance(stored, dict):
        # A list is the old format, which is still out there.
        if isinstance(stored, (list, tuple)):
            return from_legacy(stored)
        return None
    if "split" in stored:
        first = from_data(stored.get("first"))
        second = from_data(stored.get("second"))
        if first is None or second is None:
            return None
        try:
            return Split(
                orientation=stored["split"],
                first=first,
                second=second,
                sizes=stored.get("sizes") or (),
            )
        except (TypeError, ValueError):
            return None
    if "tabs" in stored:
        try:
            return TabGroup(
                documents=stored["tabs"] or (),
                current=int(stored.get("current") or 0),
            )
        except (TypeError, ValueError):
            return None
    return None
