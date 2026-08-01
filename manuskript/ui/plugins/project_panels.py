from functools import partial

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from manuskript.domain.plugin_data import PluginProjectContext


class ProjectPanelHost:
    """Host project-scoped plugin widgets and their raw files."""

    def __init__(self, window, runtime, menu=None):
        self.window = window
        self.runtime = runtime
        self.actions = {}
        self.docks = {}
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
        for contribution_id in tuple(self.docks):
            if contribution_id not in records:
                self.close_panel(contribution_id)

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
        existing = self.docks.get(contribution_id)
        if existing is not None:
            existing.show()
            existing.raise_()
            return existing

        record = next(
            (
                value
                for value in self.runtime.registry.records(
                    "project_panel"
                )
                if value.id == contribution_id
            ),
            None,
        )
        if record is None:
            return None
        contribution = record.contribution
        context = PluginProjectContext(
            plugin_id=record.plugin_id,
            project_file=self.window.currentProject,
            files=self.window.projectPluginData.namespace(
                record.plugin_id,
                on_change=self.window.projectManager.startTimerNoChanges,
            ),
            default_file=contribution.default_file,
            show_status=self.window.statusPresenter.show,
        )
        dock = QDockWidget(contribution.descriptor.name, self.window)
        dock.setObjectName(
            "pluginProjectPanel.{}".format(contribution_id)
        )
        dock.setAttribute(Qt.WA_DeleteOnClose, True)
        try:
            widget = contribution.widget_factory(context, dock)
            if not isinstance(widget, QWidget):
                raise TypeError(
                    "Project panel factories must return QWidget "
                    "instances."
                )
        except Exception as error:
            dock.deleteLater()
            QMessageBox.critical(
                self.window,
                self.window.tr("Plugin panel failed"),
                "{}\n\n{}".format(
                    contribution.descriptor.name,
                    error,
                ),
            )
            return None

        dock.setWidget(widget)
        dock.destroyed.connect(
            partial(self._dock_destroyed, contribution_id)
        )
        self.window.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.docks[contribution_id] = dock
        dock.show()
        return dock

    def close_panel(self, contribution_id):
        dock = self.docks.pop(contribution_id, None)
        if dock is not None:
            dock.close()

    def close_plugin(self, plugin_id):
        ids = [
            record.id
            for record in self.runtime.registry.records("project_panel")
            if record.plugin_id == plugin_id
        ]
        for contribution_id in ids:
            self.close_panel(contribution_id)

    def close_all(self):
        for contribution_id in tuple(self.docks):
            self.close_panel(contribution_id)
        if self.rawDataDialog is not None:
            self.rawDataDialog.close()
            self.rawDataDialog = None

    def open_raw_data(self):
        if not self._project_is_open():
            return
        if self.rawDataDialog is None:
            self.rawDataDialog = RawPluginDataDialog(
                self.window.projectPluginData,
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

    def _dock_destroyed(self, contribution_id, _object=None):
        self.docks.pop(contribution_id, None)

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
