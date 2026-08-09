"""A new half is half, not a sliver beside the editor.

Stretch factors decide how a splitter hands out space it gains, not how it
distributes what it already has: that comes from the child widgets' size
hints, and a pane built empty asks for very little. So splitting put a
sliver next to a nearly full-width editor, and the two stretch factors set
on either side of it had nothing to do until the window was resized.

The live widget, because whether a shape can actually be drawn to a given
size is not something a layout model can answer.
"""

from PyQt5.QtCore import Qt


def area(window):
    return window.mainEditor.tabSplitter


def halves_of(editor):
    """The sizes of the panes somebody can actually see.

    Nesting leaves this area's own tab widget in the splitter, hidden, so
    the raw sizes carry a zero for a pane that is not on screen.
    """
    splitter = editor.splitter
    return [
        size
        for index, size in enumerate(splitter.sizes())
        if not splitter.widget(index).isHidden()
    ]


def even_enough(sizes, tolerance=0.1):
    """Within a tenth of even, which is as exact as pixels allow.

    Qt rounds, and a pane whose contents demand a minimum can legitimately
    take a little more than its share.
    """
    if not sizes or min(sizes) <= 0:
        return False
    return (max(sizes) - min(sizes)) / float(sum(sizes)) <= tolerance


def test_a_first_split_gives_each_half_the_same_width(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    window.resize(1400, 900)
    try:
        editor.split(state=1)

        sizes = halves_of(editor)
        assert len(sizes) == 2
        assert even_enough(sizes), sizes
        assert editor.splitter.orientation() == Qt.Horizontal
    finally:
        editor.closeSplit()


def test_a_vertical_split_gives_each_half_the_same_height(MWEmptyProject):
    window = MWEmptyProject
    editor = area(window)
    window.resize(1400, 900)
    try:
        editor.split(state=2)

        assert even_enough(halves_of(editor)), halves_of(editor)
        assert editor.splitter.orientation() == Qt.Vertical
    finally:
        editor.closeSplit()


def test_dividing_this_areas_own_half_is_even_too(MWEmptyProject):
    """The nesting path arranges two panes as well, and was equally
    dependent on whatever the new child asked for.
    """
    window = MWEmptyProject
    editor = area(window)
    window.resize(1400, 900)
    try:
        editor.split(state=1)
        child = editor.divideOwnSide(Qt.Vertical)

        assert child is not None
        assert even_enough(halves_of(editor)), halves_of(editor)
    finally:
        editor.closeSplit()


def test_an_unlaid_out_area_is_left_alone(MWEmptyProject):
    """A width of zero divides into halves of zero. An arrangement being
    restored sets its own remembered sizes, and must not be handed those.
    """
    window = MWEmptyProject
    editor = area(window)
    try:
        editor.split(state=1)
        second = editor.secondTab
        second.splitter.resize(0, 0)

        assert second.equalizeSplit() is False
    finally:
        editor.closeSplit()


def test_a_restored_arrangement_keeps_the_sizes_it_remembered(
        MWEmptyProject):
    """Equalising is for a split somebody just made. A stored arrangement
    already knows how wide its halves were.
    """
    from manuskript.domain.document_area import (
        HORIZONTAL,
        Split,
        TabGroup,
        to_data,
    )
    from manuskript.ui.editors.document_area_layout import restore_area

    window = MWEmptyProject
    editor = area(window)
    window.resize(1400, 900)
    try:
        stored = Split(
            orientation=HORIZONTAL,
            first=TabGroup(documents=[], current=0),
            second=TabGroup(documents=[], current=0),
            sizes=(900, 300),
        )

        assert restore_area(editor, to_data(stored))

        # Scaled to whatever the splitter actually has, keeping the three
        # to one it was left at. Absolute pixels cannot survive a different
        # window size; the proportion is what was remembered.
        sizes = halves_of(editor)
        assert len(sizes) == 2
        assert sizes[0] > sizes[1]
        assert abs(sizes[0] / float(sizes[1]) - 3.0) < 0.2, sizes
    finally:
        editor.closeSplit()
