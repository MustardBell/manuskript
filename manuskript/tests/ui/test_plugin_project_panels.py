from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMainWindow, QMenu, QPlainTextEdit

from manuskript.domain.plugin_data import ProjectPluginData
from manuskript.plugins.api import (
    ExtensionDescriptor,
    ProjectPanelContribution,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.panels import PanelRegistry
from manuskript.ui.panels import PanelHost, PanelInstanceDirectory
from manuskript.ui.panels.window_port import PanelWindow
from manuskript.ui.plugins.project_panels import (
    ProjectPanelHost,
    RawPluginDataDialog,
)
from manuskript.ui.plugins.project_panel_views import ProjectPanelViews


class PanelTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.menuTools = QMenu(self)
        self.projectManager = MagicMock()
        self.projectManager.session.is_open = True
        self.currentProject = "/project/book.msk"
        # Plugin data belongs to the project, so it is reached through
        # the runtime that owns it rather than off this window.
        self.projectRuntime = MagicMock()
        self.projectRuntime.models.plugin_data = ProjectPluginData()
        self.statusPresenter = MagicMock()
        # Its own panel registry and host, as a workspace window has:
        # nothing builds a host for a window that has none.
        self.panelRegistry = PanelRegistry()
        self.panelHost = PanelHost(
            PanelWindow.for_window(self),
            self.panelRegistry,
            PanelInstanceDirectory(),
        )

    @property
    def pluginData(self):
        """This window's project's plugin data, for the assertions."""
        return self.projectRuntime.models.plugin_data


def panel_runtime(factory):
    registry = PluginRegistry()
    registrar = registry.registrar("example.notes")
    registrar.register_project_panel(
        ProjectPanelContribution(
            descriptor=ExtensionDescriptor(
                id="example.notes.panel",
                name="Project notes",
            ),
            widget_factory=factory,
            default_file="notes/main.txt",
        )
    )
    registry.install("example.notes", registrar.contributions)
    return SimpleNamespace(registry=registry)


def test_project_panel_receives_scoped_raw_file_context():
    received = []

    def factory(context, parent):
        received.append(context)
        return QPlainTextEdit(parent)

    window = PanelTestWindow()
    runtime = panel_runtime(factory)
    host = ProjectPanelHost(
        ProjectPanelViews.for_window(window), runtime,
    )

    dock = host.open_panel("example.notes.panel")

    assert dock is not None
    assert received[0].plugin_id == "example.notes"
    assert received[0].project_file == "/project/book.msk"
    assert received[0].default_file == "notes/main.txt"
    assert received[0].files.write(
        received[0].default_file,
        "Project note\n",
    )
    window.projectManager.startTimerNoChanges.assert_called_once_with()
    assert window.pluginData.project_files() == (
        (
            "plugins/example.notes/notes/main.txt",
            "Project note\n",
        ),
    )
    host.close_all()


def test_project_panel_host_has_no_main_window_service_locator():
    window = PanelTestWindow()
    host = ProjectPanelHost(
        ProjectPanelViews.for_window(window),
        panel_runtime(lambda _context, parent: QPlainTextEdit(parent)),
    )
    try:
        assert not hasattr(host, "window")
        assert not hasattr(host.views, "window")
    finally:
        host.close_all()
        window.close()


def test_refresh_closes_panel_when_contribution_disappears():
    window = PanelTestWindow()
    runtime = panel_runtime(
        lambda _context, parent: QPlainTextEdit(parent)
    )
    host = ProjectPanelHost(
        ProjectPanelViews.for_window(window), runtime,
    )
    host.open_panel("example.notes.panel")

    runtime.registry.remove_plugin("example.notes")
    host.refresh()

    assert host.docks == {}
    assert host.actions == {}


def test_late_container_destruction_tolerates_host_teardown():
    from manuskript.ui.panels import PanelHost, PanelInstanceDirectory

    host = PanelHost.__new__(PanelHost)

    host._container_destroyed("plugin.example.notes.example.notes.panel")


def test_raw_plugin_data_remains_editable_without_plugin():
    data = ProjectPluginData()
    data.namespace("example.missing").write(
        "source/document.txt",
        "old raw text",
    )
    changes = []
    dialog = RawPluginDataDialog(
        data,
        on_change=lambda: changes.append(True),
    )

    dialog.editor.setPlainText("new raw text")
    assert dialog.save_current()

    assert (
        data.namespace("example.missing").read("source/document.txt")
        == "new raw text"
    )
    assert changes == [True]


def test_two_hosts_declare_one_panel_and_open_their_own():
    """Every window has a host, and every host describes the same
    contributions. Declaring per window refused the second window
    outright, which is what opening a second workspace window did.
    """
    from manuskript.panels import PanelRegistry
    from manuskript.ui.panels import PanelHost, PanelInstanceDirectory

    registry = PanelRegistry()
    # One directory: these are windows of one application.
    directory = PanelInstanceDirectory()
    runtime = panel_runtime(
        lambda _context, parent: QPlainTextEdit(parent)
    )
    first_window = PanelTestWindow()
    second_window = PanelTestWindow()
    first = ProjectPanelHost(
        ProjectPanelViews.for_window(first_window), runtime,
        panel_registry=registry,
        panel_host=PanelHost(
            PanelWindow.for_window(first_window), registry, directory,
        ),
    )
    second = ProjectPanelHost(
        ProjectPanelViews.for_window(second_window), runtime,
        panel_registry=registry,
        panel_host=PanelHost(
            PanelWindow.for_window(second_window), registry, directory,
        ),
    )

    # Declared once, application scope: what exists, not who shows it.
    assert [entry.id for entry in registry.descriptors()] == [
        "plugin.example.notes.example.notes.panel",
    ]

    mine = first.open_panel("example.notes.panel")
    theirs = second.open_panel("example.notes.panel")

    assert mine is not None and theirs is not None
    assert mine is not theirs
    assert mine.widget().window() is first_window
    assert theirs.widget().window() is second_window
    assert mine.objectName() == theirs.objectName()

    # A contribution leaving is noticed by both, and undeclared once.
    runtime.registry.remove_plugin("example.notes")
    first.refresh()
    second.refresh()

    assert registry.descriptors() == ()
    assert first.docks == {} and second.docks == {}


def test_the_declaration_does_not_keep_the_declaring_window_alive():
    """The reported defect: the descriptor's widget factory was a bound
    method of the first window's host, and the registry is application
    scope, so window one lived as long as the application and every
    later window built its widget through a dead window's host.
    """
    import gc
    import weakref

    from manuskript.panels import PanelRegistry
    from manuskript.ui.panels import PanelHost, PanelInstanceDirectory

    registry = PanelRegistry()
    # One directory: these are windows of one application.
    directory = PanelInstanceDirectory()
    runtime = panel_runtime(
        lambda _context, parent: QPlainTextEdit(parent)
    )
    first_window = PanelTestWindow()
    first = ProjectPanelHost(
        ProjectPanelViews.for_window(first_window), runtime,
        panel_registry=registry,
        panel_host=PanelHost(
            PanelWindow.for_window(first_window), registry, directory,
        ),
    )
    assert "plugin.example.notes.example.notes.panel" in registry

    watch_window = weakref.ref(first_window)
    watch_host = weakref.ref(first)
    del first, first_window
    gc.collect()

    # The declaration outlives the window that made it, as it must --
    # but only the declaration.
    assert "plugin.example.notes.example.notes.panel" in registry
    assert watch_host() is None
    assert watch_window() is None


def test_a_second_window_builds_through_no_other_window():
    """With the factory application-scoped, the window doing the building
    is the only window involved -- the one named by the context.
    """
    from manuskript.panels import PanelRegistry
    from manuskript.ui.panels import PanelHost, PanelInstanceDirectory

    directory = PanelInstanceDirectory()
    seen = []

    def factory(context, parent):
        seen.append(context.project_file)
        return QPlainTextEdit(parent)

    registry = PanelRegistry()
    runtime = panel_runtime(factory)
    first_window = PanelTestWindow()
    first = ProjectPanelHost(
        ProjectPanelViews.for_window(first_window), runtime,
        panel_registry=registry,
        panel_host=PanelHost(
            PanelWindow.for_window(first_window), registry, directory,
        ),
    )
    second_window = PanelTestWindow()
    second_window.currentProject = "/project/second.msk"
    second = ProjectPanelHost(
        ProjectPanelViews.for_window(second_window), runtime,
        panel_registry=registry,
        panel_host=PanelHost(
            PanelWindow.for_window(second_window), registry, directory,
        ),
    )

    # The first host goes away entirely before the second one builds.
    first.close_all()
    del first

    assert second.open_panel("example.notes.panel") is not None
    assert seen == ["/project/second.msk"]
    second.close_all()
