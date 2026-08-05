"""The host mounts panels; descriptors only describe them.

These tests pin the dock contract inherited from the plugin panel host
it replaces: historic objectNames survive so saved layouts keep
recognising docks, and a factory that explodes costs the person a
message, not the window.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QMainWindow

from manuskript.panels import (
    PanelContext,
    PanelDescriptor,
    PanelRegistry,
)
from manuskript.ui.panels import PanelHost


def make_host(descriptor):
    window = QMainWindow()
    registry = PanelRegistry()
    registry.register(descriptor)
    return PanelHost(window, registry), window


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


def test_a_failing_factory_reports_instead_of_raising(monkeypatch):
    """The action that opens a panel must survive the panel being
    broken; the person gets told, the caller gets None.
    """
    reported = []
    monkeypatch.setattr(
        "manuskript.ui.panels.host.QMessageBox.critical",
        lambda *args: reported.append(args[2]),
    )

    def broken(context, parent):
        raise RuntimeError("no widget today")

    host, window = make_host(PanelDescriptor(
        id="core.broken",
        title="Broken",
        widget_factory=broken,
    ))

    assert host.open("core.broken", PanelContext()) is None
    assert host.instances == {}
    assert "no widget today" in reported[0]
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
