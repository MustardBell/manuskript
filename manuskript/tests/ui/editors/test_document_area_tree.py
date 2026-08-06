"""Dividing both halves of a real editor.

The editor could always split, but only ever by adding a neighbour, so
the first half stayed a bare tab group for ever. These tests use the live
widget, because whether a shape can actually be drawn is not something
the model can answer.
"""

from PyQt5.QtCore import Qt

from manuskript.domain.document_area import (
    Split,
    TabGroup,
    is_comb,
    to_data,
)
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.editors.document_area_layout import restore_area


def documents(window, count):
    """Fresh outline items to open, returning their ids."""
    root = window.mdlOutline.rootItem
    before = len(root.children())
    for number in range(count):
        outlineItem(title="Scene {}".format(number), parent=root)
    return [child.ID() for child in root.children()[before:]]


def area(window):
    return window.mainEditor.tabSplitter


def test_an_unsplit_editor_is_one_tab_group(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    try:
        assert len(editor.leaves()) == 1
        assert isinstance(editor.describe(), TabGroup)
    finally:
        editor.closeSplit()


def test_splitting_adds_a_neighbour_as_it_always_did(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    try:
        editor.split(state=1)

        assert len(editor.leaves()) == 2
        described = editor.describe()
        assert isinstance(described, Split)
        # Still a comb: the first half is a bare tab group.
        assert is_comb(described)
    finally:
        editor.closeSplit()


def test_the_first_half_can_be_divided_too(MWEmptyProject):
    """The arrangement the comb could not hold: both halves divided,
    neither side privileged.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        editor.split(state=1)
        editor.divideOwnSide(Qt.Vertical)
        editor.secondTab.divideOwnSide(Qt.Vertical)

        described = editor.describe()

        assert isinstance(described.first, Split)
        assert isinstance(described.second, Split)
        assert is_comb(described) is False
        assert len(editor.leaves()) == 4
    finally:
        editor.closeSplit()


def test_documents_move_with_the_half_they_were_in(MWEmptyProject):
    """Dividing a half must not lose what was open in it."""
    window = MWEmptyProject
    editor = area(window)
    try:
        opened = documents(window, 2)
        editor.split(state=1)
        for document in opened:
            window.mainEditor.setCurrentModelIndex(
                window.mdlOutline.getIndexByID(document),
                newTab=True,
                tabWidget=editor.tab,
            )
        assert set(editor.describe().first.documents) == set(opened)

        editor.divideOwnSide(Qt.Horizontal)

        # They are now in the child that took that half over, and none
        # of them was lost on the way.
        assert editor.firstTab is not None
        moved = editor.firstTab.describe().all_documents()
        assert set(opened) <= set(moved)
    finally:
        editor.closeSplit()


def test_every_area_holding_documents_is_reachable(MWEmptyProject):
    """Closing tabs, updating targets and counting words all walk this,
    and a divided half would be missed entirely by following
    neighbours.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        editor.split(state=1)
        editor.divideOwnSide(Qt.Vertical)

        leaves = window.mainEditor.allTabSplitters()

        assert set(leaves) == set(editor.leaves())
        # A divided area holds no documents itself, so it is not a leaf;
        # an area that merely has a neighbour still holds its own tabs.
        assert editor not in leaves
        assert editor.firstTab in leaves
    finally:
        editor.closeSplit()


def test_unsplitting_takes_every_document_back(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    opened = documents(window, 1)
    for document in opened:
        window.mainEditor.setCurrentModelIndex(
            window.mdlOutline.getIndexByID(document),
            newTab=True,
            tabWidget=editor.tab,
        )
    editor.split(state=1)
    editor.divideOwnSide(Qt.Vertical)

    editor.closeSplit()

    assert editor.firstTab is None
    assert editor.secondTab is None
    assert len(editor.leaves()) == 1
    # Everything that was open is still open, in one place.
    assert set(opened) <= set(editor.describe().documents)


def test_a_stored_tree_is_drawn_as_it_was_stored(MWEmptyProject):
    """Not flattened: the widget can hold this shape now, so restoring
    hands it over whole.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        opened = documents(window, 4)
        stored = to_data(Split(
            "vertical",
            Split(
                "horizontal",
                TabGroup([opened[0]]),
                TabGroup([opened[1]]),
            ),
            Split(
                "horizontal",
                TabGroup([opened[2]]),
                TabGroup([opened[3]]),
            ),
        ))

        assert restore_area(editor, stored) is True

        described = editor.describe()
        assert is_comb(described) is False
        assert isinstance(described.first, Split)
        assert isinstance(described.second, Split)
        # Every stored document reopened, one per quarter.
        assert set(opened) <= set(described.all_documents())
        assert len(described.groups()) == 4
    finally:
        editor.closeSplit()


def test_working_area_follows_a_split_into_the_new_half(MWEmptyProject):
    """Splitting puts the person in the pane they just made, which is
    what the recorded focus says and what dividing must not lose.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        documents(window, 1)
        editor.split(state=1)

        assert window.mainEditor.currentTabWidget() is editor.secondTab.tab

        editor.secondTab.divideOwnSide(Qt.Vertical)

        # Still inside the half that had focus, now one level deeper.
        current = window.mainEditor.currentTabWidget()
        assert current in [leaf.tab for leaf in editor.secondTab.leaves()]
    finally:
        editor.closeSplit()
