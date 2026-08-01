from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMainWindow, QMenu, QPlainTextEdit

from manuskript.domain.plugin_data import ProjectPluginData
from manuskript.plugins.api import (
    ExtensionDescriptor,
    ProjectPanelContribution,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.ui.plugins.project_panels import (
    ProjectPanelHost,
    RawPluginDataDialog,
)


class PanelTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.menuTools = QMenu(self)
        self.projectManager = MagicMock()
        self.projectManager.session.is_open = True
        self.currentProject = "/project/book.msk"
        self.projectPluginData = ProjectPluginData()
        self.statusPresenter = MagicMock()


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
    host = ProjectPanelHost(window, runtime)

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
    assert window.projectPluginData.project_files() == (
        (
            "plugins/example.notes/notes/main.txt",
            "Project note\n",
        ),
    )
    host.close_all()


def test_refresh_closes_panel_when_contribution_disappears():
    window = PanelTestWindow()
    runtime = panel_runtime(
        lambda _context, parent: QPlainTextEdit(parent)
    )
    host = ProjectPanelHost(window, runtime)
    host.open_panel("example.notes.panel")

    runtime.registry.remove_plugin("example.notes")
    host.refresh()

    assert host.docks == {}
    assert host.actions == {}


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
