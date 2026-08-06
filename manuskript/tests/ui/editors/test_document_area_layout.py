"""Reading and applying an arrangement on the editor widgets.

The model can say more than the widget can draw, on purpose: an
arrangement that splits both sides is a thing worth being able to state
and store before anything can render it. What must not happen is a
stored layout being refused, or half of it silently dropped.
"""

from unittest.mock import MagicMock

from manuskript.domain.document_area import (
    HORIZONTAL,
    VERTICAL,
    Split,
    TabGroup,
    to_data,
)
from manuskript.ui.editors.document_area_layout import (
    as_renderable,
    describe_area,
    flatten,
    read_area,
    restore_area,
)


def test_an_arrangement_is_read_off_the_editor():
    splitter = MagicMock()
    splitter.openIndexes.return_value = [
        1, ["a"], [0, ["b"], None],
    ]

    assert read_area(splitter) == Split(
        HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]),
    )
    assert describe_area(splitter) == to_data(
        Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]))
    )


def test_nothing_to_describe_is_not_an_empty_arrangement():
    """The caller falls back to what the project remembers, rather than
    recording that nothing was open.
    """
    splitter = MagicMock()
    splitter.openIndexes.return_value = None

    assert read_area(splitter) is None
    assert describe_area(splitter) is None


def test_a_stored_arrangement_is_applied_in_the_old_shape():
    """Which is the only shape the widget can currently draw."""
    splitter = MagicMock()
    area = Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]))

    assert restore_area(splitter, to_data(area)) is True

    splitter.restoreOpenIndexes.assert_called_once_with(
        [1, ["a"], [0, ["b"], None]]
    )


def test_an_arrangement_saved_by_an_older_manuskript_still_applies():
    splitter = MagicMock()

    assert restore_area(splitter, [2, ["a"], [0, ["b"], None]]) is True

    splitter.restoreOpenIndexes.assert_called_once_with(
        [2, ["a"], [0, ["b"], None]]
    )


def test_an_unreadable_arrangement_is_ignored_not_raised():
    splitter = MagicMock()

    assert restore_area(splitter, {"nonsense": True}) is False

    splitter.restoreOpenIndexes.assert_not_called()


# ------------------------------------- more than the widget can draw

def test_a_tree_keeps_every_document_when_flattened():
    """The widget cannot divide a first side, and a layout mostly
    restored beats a layout refused -- so nothing is dropped, only the
    nesting is straightened.
    """
    area = Split(
        VERTICAL,
        Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"])),
        Split(HORIZONTAL, TabGroup(["c"]), TabGroup(["d"])),
    )

    flattened = flatten(area)

    assert flattened.all_documents() == area.all_documents()
    assert len(flattened.groups()) == len(area.groups())
    # And it is now something the old format can express.
    from manuskript.domain.document_area import is_comb

    assert is_comb(flattened)


def test_a_tree_is_rendered_as_the_closest_comb():
    area = Split(
        VERTICAL,
        Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"])),
        TabGroup(["c"]),
    )

    renderable = as_renderable(area)

    # Every document still opens, in order.
    from manuskript.domain.document_area import from_legacy

    assert from_legacy(renderable).all_documents() == ("a", "b", "c")


def test_a_comb_is_rendered_unchanged():
    area = Split(
        HORIZONTAL,
        TabGroup(["a"]),
        Split(VERTICAL, TabGroup(["b"]), TabGroup(["c"])),
    )

    assert as_renderable(area) == [
        1, ["a"], [2, ["b"], [0, ["c"], None]],
    ]
