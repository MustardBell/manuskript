"""An emptied half gives its space back rather than standing there.

Closing the last document in one half of a split left the half up: an empty
tab bar and a splitter handle, holding space nothing was using and offering
nothing to do.

The live widget, because what has to happen is structural -- one half of the
split stops existing, and the documents in the other half must not be
disturbed by it.
"""

from PyQt5.QtCore import Qt


def area(window):
    return window.mainEditor.tabSplitter


def documents(window, count):
    """Fresh outline items to open, returning their ids."""
    from manuskript.models.outlineItem import outlineItem

    root = window.mdlOutline.rootItem
    before = len(root.children())
    for number in range(count):
        outlineItem(title="Scene {}".format(number), parent=root)
    return [child.ID() for child in root.children()[before:]]


def open_in(window, pane, document):
    window.mainEditor.setCurrentModelIndex(
        window.mdlOutline.getIndexByID(document),
        newTab=True,
        tabWidget=pane.tab,
    )


def close_every_tab(pane):
    """Close the tabs this pane holds now, not any it inherits on the way.

    Collapsing hands a surviving neighbour's documents to whoever absorbed
    it, and closing those too would be closing tabs nobody asked about.
    """
    for _ in range(pane.tab.count()):
        pane.closeTab(0)


def test_emptying_the_second_half_closes_the_split(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    try:
        first, second = documents(window, 2)
        editor.split(state=1)
        open_in(window, editor, first)
        open_in(window, editor.secondTab, second)
        assert len(editor.leaves()) == 2

        close_every_tab(editor.secondTab)

        assert editor.secondTab is None
        assert len(editor.leaves()) == 1
        # And the half that was still in use kept what was in it.
        assert first in editor.describe().documents
    finally:
        editor.closeSplit()
        close_every_tab(editor)


def test_emptying_the_first_half_keeps_the_others_documents(MWEmptyProject):
    """The empty half is the one that goes, whichever half it was."""
    window = MWEmptyProject
    editor = area(window)
    try:
        first, second = documents(window, 2)
        editor.split(state=1)
        open_in(window, editor, first)
        open_in(window, editor.secondTab, second)

        close_every_tab(editor)

        assert editor.secondTab is None
        assert len(editor.leaves()) == 1
        assert second in editor.describe().documents
    finally:
        editor.closeSplit()
        close_every_tab(editor)


def test_the_only_area_survives_being_emptied(MWEmptyProject):
    """An editor with nothing open is a legitimate state. It is an empty
    frame *beside something* that is not.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        only = documents(window, 1)[0]
        open_in(window, editor, only)

        close_every_tab(editor)

        assert editor.secondTab is None
        assert editor.leaves() == [editor]
        assert editor.tab.count() == 0
    finally:
        close_every_tab(editor)


def test_emptying_a_nested_half_collapses_the_nesting(MWEmptyProject):
    """A divided half that empties hands its side back, and if that leaves
    the parent's own side empty, the parent asks itself the same question.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        first, second = documents(window, 2)
        editor.split(state=1)
        open_in(window, editor.secondTab, second)
        child = editor.divideOwnSide(Qt.Vertical)
        assert child is not None
        open_in(window, child, first)

        close_every_tab(child)

        assert editor.firstTab is None
        assert second in editor.describe().all_documents()
    finally:
        editor.closeSplit()
        close_every_tab(editor)


def test_a_divided_neighbour_is_left_alone(MWEmptyProject):
    """Absorbing a divided half means rebuilding its editors, and an editor
    losing its cursor because a neighbour closed a tab is worse than the
    frame that stays behind. Recorded as a limit, not as an intention.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        first, second = documents(window, 2)
        editor.split(state=1)
        open_in(window, editor, first)
        editor.secondTab.split(state=1)
        open_in(window, editor.secondTab.secondTab, second)

        close_every_tab(editor)

        # Still there, and nothing was lost.
        assert editor.secondTab is not None
        assert second in editor.describe().all_documents()
    finally:
        editor.closeSplit()
        close_every_tab(editor)
