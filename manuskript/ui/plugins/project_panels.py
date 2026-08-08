from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from manuskript.domain.plugin_data import PluginProjectContext
from manuskript.panels import (
    DOCK,
    PER_WINDOW,
    PROJECT,
    PanelContext,
    PanelDescriptor,
    PanelRegistry,
)


def project_panel_record(runtime, contribution_id):
    """The live contribution record, looked up fresh each time.

    Fresh so that a plugin reloaded in place serves its current code
    rather than whatever was captured when the panel was declared.
    """
    return next(
        (
            value
            for value in runtime.registry.records("project_panel")
            if value.id == contribution_id
        ),
        None,
    )


def build_project_panel_widget(runtime, contribution_id, context, parent):
    """Build one window's copy of a plugin project panel.

    Deliberately a module-level function taking the application's plugin
    runtime, not a method on a window's host. The panel descriptor lives
    in the application-scope PanelRegistry, so anything its widget
    factory closes over lives as long as the application: a bound method
    here kept the first window's host -- and through it that window --
    alive for the whole session, and every later window still built its
    widget through the dead one's host.

    The per-window host supplies one narrow callback that constructs the
    public PluginProjectContext.  The application-scoped descriptor therefore
    closes over no window, and this factory can reach no window internals.
    """
    record = project_panel_record(runtime, contribution_id)
    if record is None:
        raise RuntimeError(
            "Plugin panel {} is no longer registered.".format(
                contribution_id
            )
        )
    contribution = record.contribution
    plugin_context = context.project_for_plugin(
        record.plugin_id,
        contribution.default_file,
    )
    return contribution.widget_factory(plugin_context, parent)


class ProjectPanelHost:
    """Offer project-scoped plugin panels: registry entries and a menu.

    The docks themselves are built by the window's PanelHost like any
    other panel; this class translates plugin contributions into panel
    descriptors, keeps them current as plugins come and go, and gates
    the menu on a project being open.
    """

    def __init__(
            self, window, runtime, menu=None,
            panel_registry=None, panel_host=None):
        self.window = window
        self.runtime = runtime
        self.panelRegistry = (
            panel_registry
            if panel_registry is not None
            else getattr(window, "panelRegistry", None) or PanelRegistry()
        )
        # The window's own host, never one of this class's making. Two
        # hosts for one window would each hold half its panels, and each
        # would look to the other like another window's -- so a panel
        # declared to exist once would be refused to the window that
        # already had it.
        self.panels = (
            panel_host if panel_host is not None else window.panelHost
        )
        self.actions = {}
        self._panelIds = {}
        self._owners = {}
        self.rawDataDialog = None
        self._menuEntries = []

        self._ownsMenu = menu is None
        self.menu = menu or window.menuTools.addMenu(
            window.tr("Plugins")
        )
        if self._ownsMenu:
            self.menu.setObjectName("menuPlugins")
        self.refresh()

    def refresh(self):
        records = {
            record.id: record
            for record in self.runtime.registry.records("project_panel")
        }
        for contribution_id in tuple(self._panelIds):
            if contribution_id not in records:
                self._forget(contribution_id)
        for contribution_id, record in records.items():
            if contribution_id not in self._panelIds:
                self._declare(contribution_id, record)

        for action in self._menuEntries:
            self.menu.removeAction(action)
            action.deleteLater()
        self._menuEntries = []
        self.actions = {}
        separator = self.menu.addSeparator()
        self._menuEntries.append(separator)
        for contribution_id, record in sorted(
            records.items(),
            key=lambda value: value[1].contribution.descriptor.name,
        ):
            descriptor = record.contribution.descriptor
            action = QAction(descriptor.name, self.menu)
            action.setStatusTip(descriptor.description)
            action.setData(contribution_id)
            action.triggered.connect(
                partial(self.open_panel, contribution_id)
            )
            self.menu.addAction(action)
            self._menuEntries.append(action)
            self.actions[contribution_id] = action

        self.rawDataAction = self.menu.addAction(
            self.window.tr("Raw Plugin Data…")
        )
        self._menuEntries.append(self.rawDataAction)
        self.rawDataAction.setStatusTip(
            self.window.tr(
                "View or edit portable raw files owned by project plugins"
            )
        )
        self.rawDataAction.triggered.connect(self.open_raw_data)
        self.set_project_open(self._project_is_open())

    # -------------------------------------------------- registry bridge

    def _declare(self, contribution_id, record):
        """One contribution becomes one panel the whole application sees.

        The declaration is application scope -- what exists -- while the
        widgets are per window. Every window has one of these hosts and
        every one of them describes the same contributions, so the first
        to arrive declares and the rest find it declared; declaring
        again would refuse the second window outright.

        The dock keeps its historic objectName so saved window layouts
        keep recognising it; only the panel id is new vocabulary.
        """
        panel_id = "plugin.{}.{}".format(
            record.plugin_id,
            contribution_id,
        )
        if panel_id not in self.panelRegistry:
            self.panelRegistry.register(PanelDescriptor(
                id=panel_id,
                title=record.contribution.descriptor.name,
                placement=DOCK,
                # Belongs to the project and closes with it; every
                # window builds its own from this one description.
                scope=PROJECT,
                multiplicity=PER_WINDOW,
                object_name="pluginProjectPanel.{}".format(
                    contribution_id
                ),
                # Application scope, like the descriptor holding it: the
                # plugin runtime and an id, never this host and never
                # this window. Builds against whatever window the
                # context names.
                widget_factory=partial(
                    build_project_panel_widget,
                    self.runtime,
                    contribution_id,
                ),
            ))
        self._panelIds[contribution_id] = panel_id
        self._owners[contribution_id] = record.plugin_id

    def _forget(self, contribution_id):
        """Drop a contribution that has left the runtime.

        Every window's host notices the same departure, so the panel is
        undeclared once and the others simply find it gone.
        """
        panel_id = self._panelIds.pop(contribution_id)
        self._owners.pop(contribution_id, None)
        self.panels.close(panel_id)
        if panel_id in self.panelRegistry:
            self.panelRegistry.deregister(panel_id)

    def _record(self, contribution_id):
        return project_panel_record(self.runtime, contribution_id)

    @property
    def docks(self):
        """The open dock containers, by contribution id."""
        docks = {}
        for contribution_id, panel_id in self._panelIds.items():
            instance = self.panels.instance(panel_id)
            if instance is not None:
                docks[contribution_id] = instance.container
        return docks

    def set_project_open(self, project_open):
        for action in self.actions.values():
            action.setEnabled(project_open)
        self.rawDataAction.setEnabled(project_open)
        if self._ownsMenu:
            self.menu.menuAction().setEnabled(project_open)

    def project_opened(self):
        self.set_project_open(True)

    def prepare_project_close(self):
        self.close_all()
        self.set_project_open(False)

    def open_panel(self, contribution_id):
        if not self._project_is_open():
            return None
        panel_id = self._panelIds.get(contribution_id)
        if panel_id is None:
            return None
        instance = self.panels.open(panel_id, PanelContext(
            translate=self.window.tr,
            show_status=self.window.statusPresenter.show,
            plugin_project=self._plugin_project_context,
        ))
        return instance.container if instance is not None else None

    def _plugin_project_context(self, plugin_id, default_file):
        """The project authority a plugin panel is allowed to receive."""
        window = self.window
        return PluginProjectContext(
            plugin_id=plugin_id,
            project_file=window.currentProject,
            files=window.projectRuntime.models.plugin_data.namespace(
                plugin_id,
                on_change=window.projectManager.startTimerNoChanges,
            ),
            default_file=default_file,
            show_status=window.statusPresenter.show,
        )

    def close_panel(self, contribution_id):
        panel_id = self._panelIds.get(contribution_id)
        if panel_id is not None:
            self.panels.close(panel_id)

    def close_plugin(self, plugin_id):
        ids = [
            contribution_id
            for contribution_id, owner in self._owners.items()
            if owner == plugin_id
        ]
        for contribution_id in ids:
            self.close_panel(contribution_id)

    def close_all(self):
        for contribution_id in tuple(self._panelIds):
            self.close_panel(contribution_id)
        if self.rawDataDialog is not None:
            self.rawDataDialog.close()
            self.rawDataDialog = None

    def open_raw_data(self):
        if not self._project_is_open():
            return
        if self.rawDataDialog is None:
            self.rawDataDialog = RawPluginDataDialog(
                self.window.projectRuntime.models.plugin_data,
                on_change=self.window.projectManager.startTimerNoChanges,
                parent=self.window,
            )
            self.rawDataDialog.finished.connect(
                self._raw_data_closed
            )
        self.rawDataDialog.show()
        self.rawDataDialog.raise_()
        self.rawDataDialog.activateWindow()

    def _raw_data_closed(self, _result):
        if self.rawDataDialog is not None:
            self.rawDataDialog.deleteLater()
        self.rawDataDialog = None

    def _project_is_open(self):
        manager = getattr(self.window, "projectManager", None)
        return bool(
            manager is not None
            and manager.session.is_open
        )


class RawPluginDataDialog(QDialog):
    """Fallback text editor for portable plugin-owned project files."""

    def __init__(self, plugin_data, on_change, parent=None):
        super().__init__(parent)
        self.plugin_data = plugin_data
        self.on_change = on_change
        self.currentPath = None
        self.currentBinary = False
        self.setWindowTitle(self.tr("Raw Plugin Data"))
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        explanation = QLabel(
            self.tr(
                "These files remain in the project even when their plugin "
                "is unavailable. Text files can be edited here without "
                "interpreting their format."
            )
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        splitter = QSplitter(self)
        layout.addWidget(splitter, 1)
        self.fileList = QListWidget(splitter)
        self.editor = QPlainTextEdit(splitter)
        self.editor.setEnabled(False)

        action_layout = QHBoxLayout()
        self.saveButton = QPushButton(self.tr("Save Raw Text"))
        self.saveButton.setEnabled(False)
        action_layout.addStretch(1)
        action_layout.addWidget(self.saveButton)
        layout.addLayout(action_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

        self.fileList.currentItemChanged.connect(
            self._selection_changed
        )
        self.saveButton.clicked.connect(self.save_current)
        self._populate()

    def _populate(self):
        self.fileList.clear()
        for path, _content in self.plugin_data.project_files():
            item = QListWidgetItem(path)
            item.setData(Qt.UserRole, path)
            self.fileList.addItem(item)
        if self.fileList.count():
            self.fileList.setCurrentRow(0)

    def _selection_changed(self, item, _previous=None):
        self.currentPath = (
            item.data(Qt.UserRole) if item is not None else None
        )
        self.currentBinary = False
        if self.currentPath is None:
            self.editor.clear()
            self.editor.setEnabled(False)
            self.saveButton.setEnabled(False)
            return
        content = dict(self.plugin_data.project_files())[
            self.currentPath
        ]
        if isinstance(content, bytes):
            self.currentBinary = True
            self.editor.setPlainText(
                self.tr(
                    "Binary plugin data ({} bytes) is preserved but "
                    "cannot be edited as text."
                ).format(len(content))
            )
            self.editor.setEnabled(False)
            self.saveButton.setEnabled(False)
            return
        self.editor.setEnabled(True)
        self.editor.setPlainText(content)
        self.saveButton.setEnabled(True)

    def save_current(self):
        if self.currentPath is None or self.currentBinary:
            return False
        _plugins, plugin_id, relative_path = self.currentPath.split(
            "/",
            2,
        )
        namespace = self.plugin_data.namespace(
            plugin_id,
            on_change=self.on_change,
        )
        return namespace.write(
            relative_path,
            self.editor.toPlainText(),
        )
