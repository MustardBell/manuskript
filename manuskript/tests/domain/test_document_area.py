"""What arrangements of the document area can be said.

The editor could always split, but only down one side: every area held a
tab group and at most one neighbour. That is a comb. These tests are
mostly about the shape the comb could not express -- both sides of a
split divided independently -- and about converting what is already
stored without guessing.
"""

import pytest

from manuskript.domain.document_area import (
    HORIZONTAL,
    VERTICAL,
    Split,
    TabGroup,
    from_data,
    from_legacy,
    is_comb,
    to_data,
)


def test_a_tab_group_is_the_documents_open_in_one_place():
    group = TabGroup(documents=["a", "b", "c"], current=1)

    assert group.all_documents() == ("a", "b", "c")
    assert group.current_document == "b"
    assert group.groups() == (group,)


def test_a_stale_current_tab_is_clamped_rather_than_trusted():
    """A stored arrangement can outlive the documents it names."""
    assert TabGroup(documents=["a"], current=7).current_document == "a"
    assert TabGroup(documents=["a"], current=-3).current_document == "a"
    assert TabGroup().current_document is None


def test_both_sides_of_a_split_can_be_split_independently():
    """The arrangement the comb could not express, and the reason for
    the model: four tab groups, no side privileged over the other.
    """
    left = Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]))
    right = Split(HORIZONTAL, TabGroup(["c"]), TabGroup(["d"]))
    area = Split(VERTICAL, left, right)

    assert area.all_documents() == ("a", "b", "c", "d")
    assert len(area.groups()) == 4
    assert is_comb(area) is False


def test_an_arrangement_the_old_format_could_make_is_still_a_comb():
    area = Split(
        HORIZONTAL,
        TabGroup(["a"]),
        Split(VERTICAL, TabGroup(["b"]), TabGroup(["c"])),
    )

    assert is_comb(area) is True
    assert area.all_documents() == ("a", "b", "c")


def test_a_split_must_say_which_way():
    with pytest.raises(ValueError, match="horizontal or vertical"):
        Split("diagonal", TabGroup(), TabGroup())


# ------------------------------------------------------------- the comb

def test_an_unsplit_legacy_area_is_one_tab_group():
    assert from_legacy([0, ["a", "b"], None]) == TabGroup(["a", "b"])


def test_legacy_split_states_are_the_orientations_they_meant():
    horizontal = from_legacy([1, ["a"], [0, ["b"], None]])
    vertical = from_legacy([2, ["a"], [0, ["b"], None]])

    assert horizontal == Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]))
    assert vertical == Split(VERTICAL, TabGroup(["a"]), TabGroup(["b"]))


def test_a_legacy_comb_of_three_becomes_two_nested_splits():
    area = from_legacy([1, ["a"], [2, ["b"], [0, ["c"], None]]])

    assert area == Split(
        HORIZONTAL,
        TabGroup(["a"]),
        Split(VERTICAL, TabGroup(["b"]), TabGroup(["c"])),
    )
    assert is_comb(area)


def test_a_legacy_split_with_nothing_beside_it_was_no_split():
    """The old format recorded a split state even when the neighbour was
    absent, which described a division of one thing.
    """
    assert from_legacy([1, ["a"], None]) == TabGroup(["a"])
    assert from_legacy([2, [], None]) == TabGroup()
    assert from_legacy([]) == TabGroup()
    assert from_legacy(None) == TabGroup()




def test_any_arrangement_round_trips_through_stored_data():
    area = Split(
        VERTICAL,
        Split(HORIZONTAL, TabGroup(["a"], current=0), TabGroup(["b"])),
        Split(HORIZONTAL, TabGroup(["c"]), TabGroup(["d"], current=0)),
        sizes=(200, 300),
    )

    assert from_data(to_data(area)) == area


def test_stored_data_survives_being_json(tmp_path):
    import json

    area = Split(HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]), sizes=(1, 2))

    assert from_data(json.loads(json.dumps(to_data(area)))) == area


def test_the_old_stored_shape_is_still_understood():
    """Somebody's saved layout is a list, not a mapping, and reading it
    is what stops their arrangement being lost on upgrade.
    """
    assert from_data([1, ["a"], [0, ["b"], None]]) == Split(
        HORIZONTAL, TabGroup(["a"]), TabGroup(["b"]),
    )


def test_unreadable_data_is_nothing_rather_than_an_error():
    """An arrangement is a convenience; losing it must not stop somebody
    opening their project.
    """
    for broken in (None, "", 7, {}, {"split": "sideways"},
                   {"split": HORIZONTAL, "first": {"tabs": []}}):
        assert from_data(broken) is None
