"""The pane's mode control walks the modes it was given, and nothing else.

Which modes exist, and in what order, belongs to whatever configured the
leaf -- a page type, a markup profile, and in time a plugin. A control that
knows a favourite pair stops reaching anything it was not told about, so this
one only ever asks for the next one along.
"""

from manuskript.ui.editors.markdownModeToolButton import (
    MarkdownModeToolButton,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    MarkdownPresentationState,
)


SOURCE = MarkdownPresentationMode.SOURCE
FORMATTED = MarkdownPresentationMode.FORMATTED_SOURCE
PREVIEW = MarkdownPresentationMode.LIVE_PREVIEW
CLEAN = MarkdownPresentationMode.CLEAN_EDITING
READING = MarkdownPresentationMode.READING


def button_for(modes, mode=None):
    state = MarkdownPresentationState(mode or modes[0])
    state.set_allowed_modes(modes)
    state.set_mode(mode or modes[0])
    return MarkdownModeToolButton(state), state


def test_a_click_moves_to_the_next_allowed_mode():
    button, state = button_for((SOURCE, FORMATTED, READING), SOURCE)

    button.cycleMode()
    assert state.mode is FORMATTED

    button.cycleMode()
    assert state.mode is READING


def test_the_cycle_wraps_rather_than_stopping():
    button, state = button_for((SOURCE, FORMATTED, READING), READING)

    button.cycleMode()

    assert state.mode is SOURCE


def test_the_cycle_follows_the_order_it_was_given():
    """Order is a decision made elsewhere; the button does not re-sort it."""

    button, state = button_for((READING, SOURCE, CLEAN), READING)

    button.cycleMode()

    assert state.mode is SOURCE


def test_a_mode_removed_from_this_leaf_is_never_reached():
    button, state = button_for((SOURCE, FORMATTED), FORMATTED)

    button.cycleMode()

    assert state.mode is SOURCE
    assert READING not in state.allowed_modes


def test_one_available_mode_leaves_the_pane_where_it_is():
    button, state = button_for((SOURCE,), SOURCE)

    button.cycleMode()

    assert state.mode is SOURCE
    assert "only mode" in button.toolTip()


def test_the_menu_offers_exactly_the_modes_on_offer():
    button, state = button_for((SOURCE, READING), SOURCE)

    assert [action.text() for action in button.menu().actions()] == [
        "Source", "Reading",
    ]

    state.set_allowed_modes((SOURCE, FORMATTED, PREVIEW))

    assert [action.text() for action in button.menu().actions()] == [
        "Source", "Formatted Source", "Live Preview",
    ]


def test_the_tooltip_names_where_a_click_would_go():
    button, _state = button_for((SOURCE, READING), SOURCE)

    assert button.toolTip() == "Switch to Reading"


def test_a_mode_this_build_has_never_seen_still_gets_a_name():
    assert MarkdownModeToolButton.labelFor("vendor.diagram-view") == (
        "Vendor.Diagram View"
    )
