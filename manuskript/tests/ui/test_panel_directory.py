"""Where the application's open panels are, without global state.

A panel declared to exist once in the application has to be findable in
whichever window has it. That knowledge used to be a class attribute on
PanelHost -- a WeakSet every host added itself to on construction -- which
made it reachable from anywhere that could import the class, and made two
hosts in a test see each other however carefully the test had built them
apart.
"""

import gc
import inspect

from PyQt5.QtWidgets import QLabel, QMainWindow

from manuskript.panels import (
    SINGLETON,
    PanelContext,
    PanelDescriptor,
    PanelRegistry,
)
from manuskript.ui.panels import (
    PanelHost,
    PanelInstanceDirectory,
    host as host_module,
)
from manuskript.ui.panels.window_port import PanelWindow


def label_factory(context, parent):
    return QLabel("panel body", parent)


def a_registry(descriptor):
    registry = PanelRegistry()
    registry.register(descriptor)
    return registry


def test_a_host_is_in_the_directory_it_was_given():
    directory = PanelInstanceDirectory()
    window = QMainWindow()

    host = PanelHost(PanelWindow.for_window(window), PanelRegistry(), directory)

    assert host in directory.hosts
    assert host.directory is directory
    window.close()


def test_the_holder_of_a_panel_is_never_the_host_asking():
    """The asking host has already looked at what it holds itself; being
    told about its own panel would refuse it its own panel.
    """
    registry = a_registry(PanelDescriptor(
        id="vendor.only-one",
        title="Only one",
        multiplicity=SINGLETON,
        widget_factory=label_factory,
    ))
    directory = PanelInstanceDirectory()
    first_window, second_window = QMainWindow(), QMainWindow()
    first = PanelHost(PanelWindow.for_window(first_window), registry, directory)
    second = PanelHost(PanelWindow.for_window(second_window), registry, directory)

    assert first.open("vendor.only-one", PanelContext()) is not None

    assert directory.holder("vendor.only-one", besides=first) is None
    assert directory.holder("vendor.only-one", besides=second) is first
    assert directory.locate("vendor.only-one") == (first,)

    second_window.close()
    first_window.close()


def test_two_directories_are_two_applications():
    """Which is what the class attribute could not express: hosts built
    apart still saw each other, so a test could not have two applications
    and neither could anything else.
    """
    registry = a_registry(PanelDescriptor(
        id="vendor.only-one",
        title="Only one",
        multiplicity=SINGLETON,
        widget_factory=label_factory,
    ))
    first_window, second_window = QMainWindow(), QMainWindow()
    first = PanelHost(
        PanelWindow.for_window(first_window),
        registry,
        PanelInstanceDirectory(),
    )
    second = PanelHost(
        PanelWindow.for_window(second_window),
        registry,
        PanelInstanceDirectory(),
    )

    assert first.open("vendor.only-one", PanelContext()) is not None
    # Refused nothing: as far as this host's application is concerned,
    # the panel is not open anywhere.
    assert second.open("vendor.only-one", PanelContext()) is not None

    second_window.close()
    first_window.close()


def test_a_closed_window_stops_being_findable():
    """Held weakly on purpose: a directory that kept hosts alive would
    keep their windows alive, and every window ever opened would go on
    answering for panels nobody can see.
    """
    directory = PanelInstanceDirectory()
    window = QMainWindow()
    host = PanelHost(PanelWindow.for_window(window), PanelRegistry(), directory)

    assert len(directory.hosts) == 1

    del host
    gc.collect()

    assert directory.hosts == ()
    window.close()


def test_a_host_removed_from_the_directory_is_no_longer_asked():
    directory = PanelInstanceDirectory()
    window = QMainWindow()
    host = PanelHost(PanelWindow.for_window(window), PanelRegistry(), directory)

    directory.remove(host)

    assert directory.hosts == ()
    # Removing something twice is not an error: a window may be let go of
    # more than once on the way down.
    directory.remove(host)
    window.close()


def test_no_panel_host_is_findable_through_the_class():
    """The state is an object's, not the class's. While it was the
    class's, anything that could import PanelHost could enumerate every
    window's panels -- the shape a service locator grows from.
    """
    assert not hasattr(PanelHost, "_hosts")
    assert "weakref" not in inspect.getsource(host_module)
