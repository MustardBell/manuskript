"""The host mounts panels; descriptors only describe them.

These tests pin the dock contract inherited from the plugin panel host
it replaces: historic objectNames survive so saved layouts keep
recognising docks, and a factory that explodes costs the person a
message, not the window.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QLabel, QMainWindow

from manuskript.panels import (
    PanelContext,
    PanelDescriptor,
    PanelRegistry,
)
from manuskript.ui.panels import PanelHost, PanelInstanceDirectory


def make_host(descriptor):
    window = QMainWindow()
    registry = PanelRegistry()
    registry.register(descriptor)
    return PanelHost(window, registry, PanelInstanceDirectory()), window


def label_factory(context, parent):
    return QLabel("panel body", parent)


def test_a_dock_panel_keeps_its_declared_object_name():
    """Window layouts are saved against dock objectNames, so the name a
    dock always had must survive its move into the panel vocabulary.
    """
    host, window = make_host(PanelDescriptor(
        id="plugin.example.notes",
        title="Notes",
        object_name="pluginProjectPanel.example.notes.panel",
        widget_factory=label_factory,
    ))

    instance = host.open("plugin.example.notes", PanelContext())

    dock = instance.container
    assert dock.objectName() == "pluginProjectPanel.example.notes.panel"
    assert dock.testAttribute(Qt.WA_DeleteOnClose)
    assert window.dockWidgetArea(dock) == Qt.RightDockWidgetArea
    assert instance.widget.text() == "panel body"
    assert instance.host is host
    window.close()


def test_opening_twice_reuses_the_living_instance():
    host, window = make_host(PanelDescriptor(
        id="core.notes",
        title="Notes",
        widget_factory=label_factory,
    ))

    first = host.open("core.notes", PanelContext())
    second = host.open("core.notes", PanelContext())

    assert first is second
    assert len(host.instances) == 1
    window.close()


def test_a_failing_factory_reports_instead_of_raising():
    """The action that opens a panel must survive the panel being
    broken; the person gets told, the caller gets None.

    Told, not asked. A modal dialog here made every factory fault wait
    for somebody, which in a test run is a hang rather than a failure --
    the suite stopped at the same place twice before I believed it.
    """
    reported = []

    def broken(context, parent):
        raise RuntimeError("no widget today")

    host, window = make_host(PanelDescriptor(
        id="core.broken",
        title="Broken",
        widget_factory=broken,
    ))

    assert host.open(
        "core.broken",
        PanelContext(show_status=lambda *args: reported.append(args)),
    ) is None
    assert host.instances == {}
    assert "no widget today" in reported[0][0]
    window.close()


def test_a_failing_factory_never_waits_for_anybody():
    """No modal, even with nowhere to report to. A panel that cannot be
    built must not be able to stop the application.
    """
    def broken(context, parent):
        raise RuntimeError("no widget today")

    host, window = make_host(PanelDescriptor(
        id="core.silent",
        title="Silent",
        widget_factory=broken,
    ))

    # No status reporter anywhere: still returns, still does not block.
    assert host.open("core.silent", PanelContext()) is None
    window.close()


def test_close_forgets_the_instance():
    host, window = make_host(PanelDescriptor(
        id="core.notes",
        title="Notes",
        widget_factory=label_factory,
    ))
    host.open("core.notes", PanelContext())

    host.close("core.notes")

    assert host.instance("core.notes") is None
    window.close()


def test_a_dock_is_restored_by_name_before_being_placed():
    """Panels are built when asked for, long after the window applied
    its saved layout, and QMainWindow.restoreState can only place docks
    that existed when it ran. So a later dock asks to be restored by
    name -- and it has to ask before being added to an area, because
    adding it first commits it there and makes the restore do nothing
    while still reporting success.
    """
    window = QMainWindow()
    window.setCentralWidget(QLabel("body"))
    # A layout in which this panel sat on the left.
    seed = QDockWidget("Notes", window)
    seed.setObjectName("panel.vendor.notes")
    seed.setWidget(QLabel("n"))
    window.addDockWidget(Qt.LeftDockWidgetArea, seed)
    saved = window.saveState()
    seed.setParent(None)

    later = QMainWindow()
    later.setCentralWidget(QLabel("body"))
    later.restoreState(saved)
    registry = PanelRegistry()
    registry.register(PanelDescriptor(
        id="vendor.notes",
        title="Notes",
        widget_factory=label_factory,
    ))
    host = PanelHost(later, registry, PanelInstanceDirectory())

    instance = host.open("vendor.notes", PanelContext())

    assert later.dockWidgetArea(instance.container) == (
        Qt.LeftDockWidgetArea
    )
    later.close()
    window.close()


def test_a_dock_the_layout_never_saw_goes_to_its_default_area():
    window = QMainWindow()
    window.setCentralWidget(QLabel("body"))
    registry = PanelRegistry()
    registry.register(PanelDescriptor(
        id="vendor.fresh",
        title="Fresh",
        widget_factory=label_factory,
    ))
    host = PanelHost(window, registry, PanelInstanceDirectory())

    instance = host.open("vendor.fresh", PanelContext())

    assert window.dockWidgetArea(instance.container) == (
        Qt.RightDockWidgetArea
    )
    window.close()


def test_a_singleton_panel_is_refused_a_second_window():
    """It exists once in the application, so a second window can only
    be given the one that exists -- moved, not duplicated.
    """
    import pytest

    from manuskript.panels import SINGLETON
    from manuskript.ui.panels import PanelScopeError

    registry = PanelRegistry()
    registry.register(PanelDescriptor(
        id="vendor.only-one",
        title="Only one",
        multiplicity=SINGLETON,
        widget_factory=label_factory,
    ))
    first_window, second_window = QMainWindow(), QMainWindow()
    # One directory: two windows of one application. Two would be two
    # applications, and the panel would be nobody else's business.
    directory = PanelInstanceDirectory()
    first = PanelHost(first_window, registry, directory)
    second = PanelHost(second_window, registry, directory)

    assert first.open("vendor.only-one", PanelContext()) is not None

    with pytest.raises(PanelScopeError, match="vendor.only-one"):
        second.open("vendor.only-one", PanelContext())

    # Released by the one that had it, it can be adopted by the other.
    released = first.release("vendor.only-one")
    assert second.adopt(released) is not None
    assert second.instance("vendor.only-one") is not None

    second_window.close()
    first_window.close()


def test_a_per_window_panel_is_built_once_per_window():
    registry = PanelRegistry()
    registry.register(PanelDescriptor(
        id="vendor.each",
        title="Each",
        widget_factory=label_factory,
    ))
    first_window, second_window = QMainWindow(), QMainWindow()
    # One directory: two windows of one application. Two would be two
    # applications, and the panel would be nobody else's business.
    directory = PanelInstanceDirectory()
    first = PanelHost(first_window, registry, directory)
    second = PanelHost(second_window, registry, directory)

    mine = first.open("vendor.each", PanelContext())
    theirs = second.open("vendor.each", PanelContext())

    assert mine is not theirs
    assert mine.widget is not theirs.widget

    second_window.close()
    first_window.close()


def test_a_place_is_kept_while_a_panel_is_away():
    """A panel whose plugin is missing keeps its position, and keeps it
    across further sessions without the plugin.

    Qt does this itself: saveState keeps the entry for a dock it restored
    but never found. Pinned because it was easy to assume otherwise, and
    the assumption invites a placeholder-dock scheme that would put a
    widget on screen to solve a problem that does not exist.
    """
    name = "panel.vendor.away"
    registry = PanelRegistry()
    registry.register(PanelDescriptor(
        id="vendor.away",
        title="Away",
        object_name=name,
        widget_factory=label_factory,
    ))

    # A session in which the panel exists, moved off its default area.
    present = QMainWindow()
    present.setCentralWidget(QLabel("body"))
    instance = PanelHost(present, registry, PanelInstanceDirectory()).open(
        "vendor.away", PanelContext(),
    )
    present.addDockWidget(Qt.LeftDockWidgetArea, instance.container)
    blob = present.saveState()

    # Two sessions in which it cannot be built at all.
    for _ in range(2):
        absent = QMainWindow()
        absent.setCentralWidget(QLabel("body"))
        absent.restoreState(blob)
        blob = absent.saveState()
        absent.close()

    # It comes back to where it was left.
    returned = QMainWindow()
    returned.setCentralWidget(QLabel("body"))
    returned.restoreState(blob)
    again = PanelHost(returned, registry, PanelInstanceDirectory()).open(
        "vendor.away", PanelContext(),
    )

    assert returned.dockWidgetArea(again.container) == (
        Qt.LeftDockWidgetArea
    )
    returned.close()
    present.close()
