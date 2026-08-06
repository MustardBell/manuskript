"""Read and apply a document arrangement on the editor widgets.

:mod:`manuskript.domain.document_area` says what an arrangement is; this
says how one is read off the live editor and put back. Keeping the two
apart is what lets an arrangement be stored, compared and migrated with
no application running.

The editor describes and restores arrangements itself, since it is the
only thing that knows whether a half has been divided. What lives here is
the small amount of reconciling between it and stored data.
"""

import logging

from manuskript.domain.document_area import from_data, to_data


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
    """The arrangement this editor is in, as a model node."""
    return splitter.describe()


def restore_area(splitter, stored):
    """Put the editor into a stored arrangement.

    Returns whether anything was applied. An arrangement that cannot be
    read is not applied and not complained about beyond a log line --
    losing a layout must not stop somebody opening their project.
    Arrangements written by an older Manuskript are understood, because
    old stored data is real where old widgets are not.
    """
    node = from_data(stored)
    if node is None:
        LOGGER.warning(
            "Ignoring an unreadable document arrangement.",
        )
        return False
    splitter.restore(node)
    return True
