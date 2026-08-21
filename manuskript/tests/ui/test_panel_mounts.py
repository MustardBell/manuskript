"""How a panel is fastened is one class per way, asked rather than known.

A dock used to be built from scratch in three places -- opening a panel,
adopting one from another window, tearing one off -- each of which had to
agree about its object name, its delete-on-close attribute and asking Qt
to restore its saved position before putting it anywhere. The last time
they disagreed, a moved panel's toggle emptied its dock and left the frame
standing.
"""

import inspect

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDockWidget,
    QLabel,
    QMainWindow,
    QSplitter,
)

from manuskript.panels import (
    DOCK,
    SPLITTER_SLOT,
    PanelContext,
    ToolPanelDescriptor,
    PanelRegistry,
    SplitterSlot,
)
from manuskript.ui.panels import host as host_module
from manuskript.ui.panels import PanelHost, PanelInstanceDirectory
from manuskript.ui.panels.window_port import PanelWindow
from manuskript.ui.panels.mounts import (
    DockMount,
    SplitterMount,
    dock_name,
    mounts_for,
)


def label_factory(context, parent):
    return QLabel("panel body", parent)


def a_host(descriptor):
    window = QMainWindow()
    window.setCentralWidget(QLabel("body"))
    registry = PanelRegistry()
    registry.register(descriptor)
    return PanelHost(
        PanelWindow.for_window(window),
        registry,
        PanelInstanceDirectory(),
    ), window


# ------------------------------------------------------------ the mounts


def test_a_dock_answers_to_the_name_its_panel_declares():
    declared = ToolPanelDescriptor(
        id="plugin.example.notes",
        title="Notes",
        object_name="pluginProjectPanel.example.notes.panel",
    )
    undeclared = ToolPanelDescriptor(id="core.notes", title="Notes")

    assert dock_name(declared) == "pluginProjectPanel.example.notes.panel"
    assert dock_name(undeclared) == "panel.core.notes"


def test_a_splitter_mount_puts_a_panel_in_the_slot_it_names():
    window = QMainWindow()
    splitter = QSplitter(window)
    splitter.setObjectName("splitterTest")
    splitter.addWidget(QLabel("first"))
    splitter.addWidget(QLabel("second"))
    descriptor = ToolPanelDescriptor(
        id="core.slotted",
        title="Slotted",
        placement=SPLITTER_SLOT,
        slot=SplitterSlot("splitterTest", 1),
    )
    mount = SplitterMount(PanelWindow.for_window(window))

    parent, container = mount.prepare(descriptor)
    widget = QLabel("mine", parent)
    mount.install(descriptor, widget, container)

    assert parent is splitter
    # No container: the widget sits in the splitter itself.
    assert container is None
    assert splitter.indexOf(widget) == 1
    window.close()


def test_panel_window_inventories_splitters_once_at_composition():
    class CountingWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.splitter_searches = 0

        def findChildren(self, *args, **kwargs):
            self.splitter_searches += 1
            return super().findChildren(*args, **kwargs)

    window = CountingWindow()
    splitter = QSplitter(window)
    splitter.setObjectName("splitterStable")

    views = PanelWindow.for_window(window)

    assert views.find_splitter("splitterStable") is splitter
    assert views.find_splitter("splitterStable") is splitter
    assert window.splitter_searches == 1
    window.close()


def test_a_splitter_this_window_has_not_got_says_so():
    import pytest

    descriptor = ToolPanelDescriptor(
        id="core.missing",
        title="Missing",
        placement=SPLITTER_SLOT,
        slot=SplitterSlot("splitterAbsent", 0),
    )
    mount = SplitterMount(PanelWindow.for_window(QMainWindow()))

    assert mount.find(descriptor) is None
    with pytest.raises(LookupError, match="splitterAbsent"):
        mount.prepare(descriptor)


def test_a_dock_panel_is_in_no_splitter():
    """Asked merely to find out, so it answers rather than raising: two
    callers want to know whether a panel sits in a splitter at all.
    """
    mount = SplitterMount(PanelWindow.for_window(QMainWindow()))

    assert mount.find(ToolPanelDescriptor(id="core.docked", title="D")) is None


def test_a_dock_mount_makes_the_container_the_widget_is_built_into():
    window = QMainWindow()
    window.setCentralWidget(QLabel("body"))
    descriptor = ToolPanelDescriptor(id="core.notes", title="Notes")
    mount = DockMount(PanelWindow.for_window(window))

    parent, container = mount.prepare(descriptor)
    widget = QLabel("mine", parent)
    mount.install(descriptor, widget, container)

    assert parent is container
    assert container.objectName() == "panel.core.notes"
    # The X puts the panel away; a panel the window still owns must not
    # be destroyed by it, or its toggle has nothing to bring back.
    assert not container.testAttribute(Qt.WA_DeleteOnClose)
    assert container.widget() is widget
    assert window.dockWidgetArea(container) == Qt.RightDockWidgetArea
    window.close()


def test_a_floating_dock_keeps_the_name_it_has_when_docked():
    """Qt records floating state against the object name, so two names
    would mean a panel left floating came back docked.
    """
    window = QMainWindow()
    descriptor = ToolPanelDescriptor(id="core.notes", title="Notes")
    mount = DockMount(PanelWindow.for_window(window))

    _parent, container = mount.prepare(descriptor)
    mount.install_floating(descriptor, QLabel("mine"), container)

    assert container.isFloating()
    assert container.objectName() == dock_name(descriptor)
    window.close()


def test_a_window_can_mount_every_placement_a_panel_may_declare():
    """A placement with no mount would be a panel nothing could open."""
    mounts = mounts_for(PanelWindow.for_window(QMainWindow()))

    from manuskript.panels import PLACEMENTS

    assert set(mounts) == set(PLACEMENTS)


# -------------------------------------------------------- and the host


def test_the_host_builds_no_dock_of_its_own():
    """It built one in three places. Each had to agree with the others
    about the name, the attribute and asking Qt for the saved position.
    """
    source = inspect.getsource(host_module)

    for named in ("QDockWidget", "QSplitter", "setObjectName"):
        assert named not in source, named


class RecordingMount:
    """A way of mounting that only remembers being asked."""

    placement = DOCK

    def __init__(self):
        self.prepared = []
        self.installed = []
        self.discarded = []
        # A dock, because that is what a container is today: the toggle a
        # host puts on a mounted panel follows a dock the person closes
        # with its own button, and asks the container to say when that
        # happens.
        self.container = QDockWidget()

    def prepare(self, descriptor):
        self.prepared.append(descriptor.id)
        return self.container, self.container

    def install(self, descriptor, widget, container):
        self.installed.append((descriptor.id, widget, container))

    def discard(self, container):
        self.discarded.append(container)

    def find(self, descriptor):
        return None


def test_the_host_asks_a_mount_rather_than_knowing_how():
    """Dispatch is a lookup by placement, so a third way of mounting is a
    third class and no change here.
    """
    host, window = a_host(ToolPanelDescriptor(
        id="core.notes",
        title="Notes",
        widget_factory=label_factory,
    ))
    mount = RecordingMount()
    host._mounts[DOCK] = mount

    instance = host.open("core.notes", PanelContext())

    assert mount.prepared == ["core.notes"]
    assert mount.installed[0][0] == "core.notes"
    assert instance.container is mount.container
    assert instance.widget.text() == "panel body"
    window.close()


def test_a_mount_that_never_got_its_widget_is_told_to_let_go():
    """The dock a failed panel was going to live in must not be left
    standing empty.
    """
    def broken(context, parent):
        raise RuntimeError("no widget today")

    host, window = a_host(ToolPanelDescriptor(
        id="core.broken",
        title="Broken",
        widget_factory=broken,
    ))
    mount = RecordingMount()
    host._mounts[DOCK] = mount
    reported = []

    assert host.open(
        "core.broken",
        PanelContext(show_status=lambda *args: reported.append(args)),
    ) is None

    assert mount.discarded == [mount.container]
    assert mount.installed == []
    assert host.instances == {}
    assert "no widget today" in reported[0][0]
    window.close()


def test_a_placement_this_window_cannot_mount_is_reported_not_raised():
    """A panel asking for a mounting that does not exist is still just a
    broken panel: whatever opened it carries on.
    """
    host, window = a_host(ToolPanelDescriptor(
        id="core.notes",
        title="Notes",
        widget_factory=label_factory,
    ))
    host._mounts.clear()
    reported = []

    assert host.open(
        "core.notes",
        PanelContext(show_status=lambda *args: reported.append(args)),
    ) is None

    assert host.instances == {}
    assert "core.notes" in reported[0][0] or "Notes" in reported[0][0]
    window.close()
