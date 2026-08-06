"""Read and apply a document arrangement on the editor widgets.

:mod:`manuskript.domain.document_area` says what an arrangement is; this
says how one is read off the live editor and put back. Keeping the two
apart is what lets an arrangement be stored, compared and migrated with
no application running.

The widget can currently only render a comb -- every split's first side
is a bare tab group -- so applying a real tree falls back to the closest
comb rather than refusing. The model is deliberately ahead of the widget:
an arrangement nobody can draw yet is still worth being able to say.
"""

import logging

from manuskript.domain.document_area import (
    Split,
    TabGroup,
    is_comb,
    to_data,
    to_legacy,
)


LOGGER = logging.getLogger(__name__)


def describe_area(splitter):
    """The arrangement this editor is in, as stored data.

    Returns None when there is nothing to describe, which is different
    from an empty arrangement: the caller falls back to whatever the
    project remembers rather than recording that nothing was open.
    """
    node = read_area(splitter)
    if node is None:
        return None
    return to_data(node)


def read_area(splitter):
    """The arrangement this editor is in, as a model node.

    Asks the widget to describe itself where it can, since it is the
    only thing that knows whether a side has been divided; falling back
    to the old triple for anything that cannot.
    """
    describe = getattr(splitter, "describe", None)
    if describe is not None:
        return describe()
    legacy = splitter.openIndexes()
    if not legacy:
        return None
    from manuskript.domain.document_area import from_legacy

    return from_legacy(legacy)


def restore_area(splitter, stored):
    """Put the editor into a stored arrangement.

    Returns whether anything was applied. An arrangement that cannot be
    read is not applied and not complained about beyond a log line --
    losing a layout must not stop somebody opening their project.
    """
    from manuskript.domain.document_area import from_data

    node = from_data(stored)
    if node is None:
        LOGGER.warning(
            "Ignoring an unreadable document arrangement.",
        )
        return False
    restore = getattr(splitter, "restore", None)
    if restore is not None:
        restore(node)
        return True
    # A widget that only speaks the old shape gets the closest comb.
    splitter.restoreOpenIndexes(as_renderable(node))
    return True


def as_renderable(node):
    """The arrangement in the shape the widget can draw.

    A comb passes through unchanged. A tree that splits both sides is
    flattened to the comb closest to it, because the widget has no way
    to divide a first side -- and a layout mostly restored beats a layout
    refused.
    """
    if is_comb(node):
        return to_legacy(node)
    LOGGER.info(
        "This document arrangement splits both sides; restoring the "
        "closest arrangement the editor can currently draw."
    )
    return to_legacy(flatten(node))


def flatten(node):
    """The closest comb to an arbitrary arrangement.

    Every tab group is kept, in the order it appears, and each split
    keeps the orientation of the split it came from. Nothing is dropped;
    only the nesting is straightened.
    """
    groups = node.groups()
    orientations = split_orientations(node)
    result = groups[-1]
    for group, orientation in zip(
        reversed(groups[:-1]),
        reversed(orientations),
    ):
        result = Split(
            orientation=orientation,
            first=group,
            second=result,
        )
    return result


def split_orientations(node):
    """One orientation per join, in the order the groups appear."""
    if isinstance(node, TabGroup):
        return ()
    return (
        split_orientations(node.first)
        + (node.orientation,)
        + split_orientations(node.second)
    )
