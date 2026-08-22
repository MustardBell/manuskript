from types import SimpleNamespace
from unittest.mock import MagicMock
import time

import pytest

from PyQt5.QtWidgets import QMainWindow, QMenu, QPlainTextEdit
from PyQt5.QtWidgets import qApp

from manuskript.domain.plugin_data import ProjectPluginData
from manuskript.panels import DOCK, ToolPanelDescriptor
from manuskript.plugins.api import (
    ExtensionDescriptor,
    ProjectPanelContribution,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.plugins.capabilities import CAPABILITY_QUERY_EXECUTE
from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins.ui_contract import (
    UiControl,
    UiControlKind,
    UiDocument,
)
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


def panel_runtime(factory, declared=()):
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
    return SimpleNamespace(
        registry=registry,
        declares=lambda plugin_id, name: (
            plugin_id == "example.notes" and name in declared
        ),
    )


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
    with pytest.raises(PluginScopeError, match="did not declare"):
        received[0].capability(CAPABILITY_QUERY_EXECUTE)
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


def test_a_declarative_project_panel_supplies_its_host_widget():
    """And takes no navigator row: a contribution is a tool panel.

    It used to be able to ask for one, which made a contradiction
    expressible -- a navigator row says "a place the writer goes" while the
    host built a dock regardless. A plugin wanting a navigator destination
    is asking for workspace surface semantics, and that contract does not
    exist yet.
    """

    registry = PluginRegistry()
    registrar = registry.registrar("example.notes")
    registrar.register_project_panel(ProjectPanelContribution(
        descriptor=ExtensionDescriptor(
            id="example.notes.panel",
            name="Project notes",
        ),
        default_file="notes/main.txt",
        visible_with_surfaces=("core.editor",),
        preferred_extent=333,
        ui=UiDocument("example.notes.panel", 0, (
            UiControl(
                "message",
                UiControlKind.MESSAGE,
                value="No notes yet.",
            ),
        )),
    ))
    registry.install("example.notes", registrar.contributions)
    runtime = SimpleNamespace(registry=registry, declares=lambda *_args: False)
    window = PanelTestWindow()
    host = ProjectPanelHost(ProjectPanelViews.for_window(window), runtime)

    panel_id = host._panelIds["example.notes.panel"]
    descriptor = window.panelRegistry.descriptor(panel_id)
    # A tool panel, asked of its type. It has no navigator field at all
    # now -- the absence is the type's, not a value to check.
    assert isinstance(descriptor, ToolPanelDescriptor)
    assert descriptor.placement == DOCK
    assert descriptor.visible_with_surfaces == ("core.editor",)
    assert descriptor.preferred_extent == 333
    dock = host.open_panel("example.notes.panel")
    deadline = time.monotonic() + 2
    while dock.widget().document is None:
        assert time.monotonic() < deadline
        qApp.processEvents()
        time.sleep(0.005)
    assert dock.widget().document.id == "example.notes.panel"
    host.close_all()


def test_project_panel_can_resolve_a_declared_story_service():
    received = []

    def factory(context, parent):
        received.append(context)
        return QPlainTextEdit(parent)

    window = PanelTestWindow()
    window.projectManager.storage.story_query.execute.return_value = (
        "result",
    )
    runtime = panel_runtime(factory, declared=(CAPABILITY_QUERY_EXECUTE,))
    host = ProjectPanelHost(
        ProjectPanelViews.for_window(window), runtime,
    )

    host.open_panel("example.notes.panel")
    result = received[0].capability(CAPABILITY_QUERY_EXECUTE).execute(
        "query"
    )

    assert result == ("result",)
    window.projectManager.storage.story_query.execute.assert_called_once_with(
        "query"
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


def test_a_project_panel_cannot_ask_for_a_navigator_row():
    """A contribution says tool panel, and there is no way to say otherwise.

    The field used to exist and made a contradiction expressible: a
    navigator row says "a place the writer goes", while the host built a
    dock regardless -- which under the surface/tool distinction is two
    different kinds of thing claimed at once. Nothing ever set it.

    A plugin that wants a navigator destination is asking for workspace
    surface semantics: a central host rather than a dock, no floating into
    an owned utility window, and moving between windows by changing which
    workspace owns it. That contract does not exist yet, and refusing is
    how it says so instead of handing back a dock that resembles one.
    """

    from manuskript.plugins.api import (
        ExtensionDescriptor,
        ProjectPanelContribution,
    )

    with pytest.raises(TypeError, match="navigator"):
        ProjectPanelContribution(
            descriptor=ExtensionDescriptor(id="vendor.notes", name="Notes"),
            default_file="notes.json",
            navigator=object(),
        )
