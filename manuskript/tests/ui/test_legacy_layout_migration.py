"""What a saved layout can and cannot be asked about dead docks.

Two questions were put to Qt here, and they came back with opposite
answers. The results are kept as tests because a negative result nobody
wrote down is a thing somebody tries again.

The setting: ``QMainWindow.saveState`` keeps the entry for a dock it
restored but never found, for as long as the profile lives. That is
deliberate -- a panel whose plugin is away comes back to its place -- and
it means a layout written while the seven work surfaces were docks names
seven docks this build never creates.

**Can those names be scrubbed?** No. Giving them real temporary docks so
the restore resolves them, then removing the docks and saving, leaves
every one of them still restorable. Measured on Qt 5.15.3 with four ways
of letting go -- plain ``removeDockWidget``, re-docking a floating one
first, hiding it first, and reparenting to None -- and all four leak all
of them. ``removeDockWidget`` turns a dock back into the same kind of
placeholder an unresolved name leaves.

**Can a layout be asked whether it knows a name?** Yes, and precisely: a
dock-era layout answers for all seven, an upstream-shaped one for none.
That is worth more than the scrub would have been. The gate on old
layouts currently asks what version stamped them, which gets the one
group of real readers wrong: an installation upgrading from upstream
arrives stamped version 1 and its layout names no work-surface docks at
all, because upstream's surfaces were pages rather than docks. Asking the
layout what it contains tells those apart; asking its version cannot.

The asking has to be done on a window that is then thrown away. Detection
is a restore, and a restore of a dirty layout puts the dead names into
whatever window performed it.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QLabel, QMainWindow


#: What the seven work surfaces' docks were called, while they had any.
LEGACY_SURFACE_DOCKS = (
    "panel.core.general",
    "panel.core.entities.project",
    "panel.core.entities.characters",
    "panel.core.entities.plots",
    "panel.core.entities.world",
    "panel.core.outline",
    "panel.core.editor",
)

#: The docks this build still makes.
TOOL_DOCKS = (
    "panel.core.project-tree",
    "panel.core.metadata",
    "panel.core.storyline",
)

#: What upstream's own window has, and this fork kept.
UPSTREAM_DOCKS = ("dckNavigation", "dckCheatSheet", "dckSearch")


def dock(window, name):
    """One dock, named the way saved layouts name them."""

    made = QDockWidget(name, window)
    made.setObjectName(name)
    made.setWidget(QLabel(name, made))
    return made


def a_window(names, area=Qt.LeftDockWidgetArea):
    window = QMainWindow()
    window.setCentralWidget(QLabel("central", window))
    window.resize(1280, 800)
    docks = {}
    for name in names:
        made = dock(window, name)
        window.addDockWidget(area, made)
        docks[name] = made
    return window, docks


def a_dock_era_layout():
    """A layout as the dock era wrote them, deliberately not the default.

    The tool docks are arranged in a way nothing would produce by
    accident, so a restore that quietly did nothing would show up, and
    one work surface is left floating -- a stronger statement of where a
    reader wanted something than a docked position is.
    """

    window, docks = a_window(TOOL_DOCKS + LEGACY_SURFACE_DOCKS)
    window.addDockWidget(
        Qt.RightDockWidgetArea, docks["panel.core.metadata"],
    )
    window.splitDockWidget(
        docks["panel.core.project-tree"],
        docks["panel.core.storyline"],
        Qt.Vertical,
    )
    docks["panel.core.editor"].setFloating(True)
    # Keep the synthetic floating window inside CI's smallest supported
    # 640x480 virtual display.  A 640x480 window at (120, 90) is necessarily
    # clamped to the screen origin by Qt, so it cannot preserve the position
    # this fixture is meant to exercise.
    docks["panel.core.editor"].setGeometry(120, 90, 320, 240)
    return bytes(window.saveState())


def names_known_to(blob, names=LEGACY_SURFACE_DOCKS):
    """Which of these names the layout has somewhere to put.

    On a scratch window, always: asking is restoring, and restoring a
    dock-era layout is what puts the dead names into a window.
    """

    window, _docks = a_window(TOOL_DOCKS)
    assert window.restoreState(blob)
    found = []
    for name in names:
        candidate = dock(window, name)
        if window.restoreDockWidget(candidate):
            found.append(name)
        window.removeDockWidget(candidate)
    return tuple(found)


def cleaned(blob, release):
    """Resolve the dead names with real docks, then let those docks go.

    ``release`` is how they are let go of, since the answer might have
    depended on that. It does not.
    """

    window, _docks = a_window(TOOL_DOCKS)
    temporary = {}
    for name in LEGACY_SURFACE_DOCKS:
        made = dock(window, name)
        window.addDockWidget(Qt.LeftDockWidgetArea, made)
        temporary[name] = made

    assert window.restoreState(blob)

    floating = {
        name: made.isFloating() for name, made in temporary.items()
    }
    for made in temporary.values():
        release(window, made)
    return bytes(window.saveState()), floating


# ----------------------------------------------------- what does work


def test_a_layout_says_which_dock_names_it_knows():
    """The detector. Precise in both directions, which is what it needs.

    This is what a gate on old layouts should ask. Asking the version
    number instead gets upstream's readers wrong: their layout arrives
    stamped 1 and is perfectly clean.
    """

    dock_era = a_dock_era_layout()
    upstream, _docks = a_window(UPSTREAM_DOCKS)
    current, _docks = a_window(TOOL_DOCKS)

    assert names_known_to(dock_era) == LEGACY_SURFACE_DOCKS
    assert names_known_to(bytes(upstream.saveState())) == ()
    assert names_known_to(bytes(current.saveState())) == ()


def test_temporary_docks_recover_the_readers_own_arrangement():
    """The half of the idea that works: the restore resolves.

    What refusing an old layout outright costs is exactly this -- where
    the reader had put the panels they still have.
    """

    blob = a_dock_era_layout()

    window, _docks = a_window(TOOL_DOCKS)
    for name in LEGACY_SURFACE_DOCKS:
        window.addDockWidget(Qt.LeftDockWidgetArea, dock(window, name))

    assert window.restoreState(blob)
    assert window.dockWidgetArea(
        window.findChild(QDockWidget, "panel.core.metadata")
    ) == Qt.RightDockWidgetArea
    # And a surface the reader had torn out is legible while it is here,
    # which is worth recording before anything is thrown away.
    assert window.findChild(QDockWidget, "panel.core.editor").isFloating()


# ------------------------------------------------- what does not work


def test_letting_the_temporary_docks_go_does_not_scrub_the_names():
    """The negative result, in four ways of letting go.

    ``removeDockWidget`` turns a dock back into the same kind of
    placeholder an unresolved name leaves, so the identity survives into
    the next save -- whether it was floating, hidden, re-docked first, or
    reparented to nothing. Measured on Qt 5.15.3.

    So a layout cannot be sanitised and handed on. It can only be applied
    with the dead names still in it, or refused.
    """

    def plain(window, made):
        window.removeDockWidget(made)

    def redocked(window, made):
        made.setFloating(False)
        window.removeDockWidget(made)

    def hidden(window, made):
        made.setFloating(False)
        made.hide()
        window.removeDockWidget(made)

    def reparented(window, made):
        window.removeDockWidget(made)
        made.setParent(None)

    blob = a_dock_era_layout()

    for release in (plain, redocked, hidden, reparented):
        scrubbed, _floating = cleaned(blob, release)
        assert names_known_to(scrubbed) == LEGACY_SURFACE_DOCKS, release


# ------------------------------------------- what the window does with it


def test_the_detector_the_window_uses_answers_the_same_way():
    """The production one, against the same layouts.

    Written separately above to establish what Qt does; this is the
    function the state controller actually asks, so the two must not
    drift apart.
    """

    from manuskript.ui.legacy_layouts import legacy_docks_in

    upstream, _docks = a_window(UPSTREAM_DOCKS)
    current, _docks = a_window(TOOL_DOCKS)

    assert legacy_docks_in(a_dock_era_layout()) == LEGACY_SURFACE_DOCKS
    assert legacy_docks_in(bytes(upstream.saveState())) == ()
    assert legacy_docks_in(bytes(current.saveState())) == ()


def test_the_detector_recovers_surface_identity_and_floating_geometry():
    """Migration keeps the stronger intent before refusing the old blob.

    The old dock itself does not survive.  Its stable surface id and ordinary
    geometry do, which is enough to make a peer workspace without teaching
    the new workspace model about obsolete docks or Qt's private byte format.
    """

    from manuskript.ui.legacy_layouts import legacy_surface_layouts_in

    layouts = legacy_surface_layouts_in(a_dock_era_layout())
    by_id = {layout.surface_id: layout for layout in layouts}

    assert tuple(by_id) == tuple(
        name.removeprefix("panel.") for name in LEGACY_SURFACE_DOCKS
    )
    assert not by_id["core.general"].floating
    editor = by_id["core.editor"]
    assert editor.floating
    assert editor.geometry == (120, 90, 320, 240)


def test_a_payload_that_will_not_restore_is_not_guessed_at():
    """Whatever is wrong with it is about to be wrong for the real
    window, which reports it by failing to restore rather than by having
    this decide what it might have been.
    """

    from manuskript.ui.legacy_layouts import legacy_docks_in

    assert legacy_docks_in(b"not a layout at all") == ()
    assert legacy_docks_in(None) == ()
    assert legacy_docks_in(b"") == ()
