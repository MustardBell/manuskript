"""One toggle per panel, driving whatever that panel is sitting in.

The thing a toggle drives depends on where the panel was mounted -- the
dock when it has one, the widget itself in a splitter -- and a panel moved
between the two changes the answer. The code that mounted a panel used to
answer from where it stood, so unchecking a panel that had been moved into
a dock emptied the dock and left the frame standing.
"""

import inspect

from PyQt5.QtWidgets import QDockWidget, QLabel, QMainWindow

from manuskript.panels import PanelDescriptor
from manuskript.ui.panels import host as host_module
from manuskript.ui.panels.host import PanelInstance
from manuskript.ui.panels.visibility import PanelVisibility
from manuskript.ui.panels.window_port import PanelWindow


def a_panel(default_visible=True):
    return PanelDescriptor(
        id="core.notes",
        title="Notes",
        default_visible=default_visible,
    )


def visibility_for(window):
    return PanelVisibility(
        PanelWindow.for_window(window).create_action
    )


def test_a_toggle_drives_the_dock_a_panel_lives_in():
    window = QMainWindow()
    dock = QDockWidget("Notes", window)
    widget = QLabel("body", dock)
    dock.setWidget(widget)
    window.addDockWidget(0x2, dock)  # right area
    instance = PanelInstance(
        descriptor=a_panel(), widget=widget, container=dock,
    )

    visibility = visibility_for(window)
    action = visibility.bind(instance)

    assert PanelVisibility.shown_thing(instance) is dock
    action.setChecked(False)
    assert dock.isHidden()
    # The widget stays in the dock: putting a panel away is not emptying
    # its frame.
    assert dock.widget() is widget
    window.close()


def test_a_toggle_drives_the_widget_where_there_is_no_dock():
    window = QMainWindow()
    widget = QLabel("body", window)
    instance = PanelInstance(descriptor=a_panel(), widget=widget)

    visibility = visibility_for(window)
    action = visibility.bind(instance)

    assert PanelVisibility.shown_thing(instance) is widget
    action.setChecked(False)
    assert widget.isHidden()
    window.close()


def test_a_panel_starts_as_its_descriptor_says():
    window = QMainWindow()
    widget = QLabel("body", window)
    instance = PanelInstance(
        descriptor=a_panel(default_visible=False), widget=widget,
    )

    action = visibility_for(window).bind(instance)

    assert action.isChecked() is False
    assert widget.isHidden()
    window.close()


def test_a_released_toggle_drives_nothing():
    """The action belongs to the window that made it. A host adopting the
    panel makes its own, and the old one must not still be moving the
    widget about.
    """
    window = QMainWindow()
    widget = QLabel("body", window)
    instance = PanelInstance(descriptor=a_panel(), widget=widget)
    visibility = visibility_for(window)
    action = visibility.bind(instance)

    visibility.unbind(instance)

    assert instance.action is None
    assert not action.isEnabled()
    action.setChecked(False)
    # Still visible: the toggle no longer speaks for this panel.
    assert not widget.isHidden()
    window.close()


def test_unbinding_twice_is_not_an_error():
    """A window may be let go of more than once on the way down."""
    window = QMainWindow()
    instance = PanelInstance(
        descriptor=a_panel(), widget=QLabel("body", window),
    )
    visibility = visibility_for(window)
    visibility.bind(instance)

    visibility.unbind(instance)
    visibility.unbind(instance)

    assert instance.action is None
    window.close()


def test_closing_a_floating_dock_unchecks_its_toggle():
    """Its own close button is the person putting the panel away, and
    every button that mirrors the toggle has to agree.
    """
    window = QMainWindow()
    dock = QDockWidget("Notes", window)
    dock.setWidget(QLabel("body", dock))
    dock.setFloating(True)
    instance = PanelInstance(
        descriptor=a_panel(), widget=dock.widget(), container=dock,
    )
    visibility = visibility_for(window)
    action = visibility.bind(instance)

    dock.visibilityChanged.emit(False)

    assert action.isChecked() is False
    window.close()


def test_a_panel_tabbed_behind_a_neighbour_is_not_put_away():
    """Qt hides a docked widget whenever another tab in the same area is
    selected. Taking that for "the person closed it" would close a panel
    merely tabbed behind its neighbour -- which is why the signal is only
    believed while the dock floats.
    """
    window = QMainWindow()
    dock = QDockWidget("Notes", window)
    dock.setWidget(QLabel("body", dock))
    window.addDockWidget(0x2, dock)
    assert not dock.isFloating()
    instance = PanelInstance(
        descriptor=a_panel(), widget=dock.widget(), container=dock,
    )
    visibility = visibility_for(window)
    action = visibility.bind(instance)

    dock.visibilityChanged.emit(False)

    assert action.isChecked() is True
    window.close()


def test_showing_a_panel_goes_through_its_own_action():
    """Every button that offers the panel mirrors that action; poking the
    widget would leave them all saying otherwise.
    """
    window = QMainWindow()
    widget = QLabel("body", window)
    instance = PanelInstance(
        descriptor=a_panel(default_visible=False), widget=widget,
    )
    visibility = visibility_for(window)
    visibility.bind(instance)

    visibility.set_visible(instance, True)

    assert instance.action.isChecked() is True
    assert not widget.isHidden()
    window.close()


def test_a_panel_with_no_toggle_is_shown_by_nobody_rather_than_crashing():
    instance = PanelInstance(descriptor=a_panel(), widget=QLabel("body"))

    PanelVisibility.set_visible(instance, True)

    assert instance.action is None


def test_the_host_makes_no_action_of_its_own():
    """Three places mounted panels and each gave the toggle its target.
    One of them answered "the widget" for a docked panel.
    """
    source = inspect.getsource(host_module)

    for named in ("QAction", "setChecked", "visibilityChanged"):
        assert named not in source, named
