from functools import partial

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction

from manuskript.media_types import MediaTypeView
from manuskript.plugins.capabilities import (
    CAPABILITY_MEDIA_REGISTRY,
    CAPABILITY_UI_EXPORT_ROUTING,
)
from manuskript.plugins.api import PluginSettingsContext
from manuskript.plugins.errors import PluginScopeError
from manuskript.ui.plugins.manager import PluginManagerDialog
from manuskript.ui.plugins.options import PluginOptionsDialog
from manuskript.ui.plugins.markup_profiles import MarkupProfileService
from manuskript.ui.plugins.page_routing import PageRoutingGateway
from manuskript.ui.plugins.page_types import PageTypeService
from manuskript.ui.plugins.routing_panel import ExportRoutingService
from manuskript.ui.plugins.project_panels import ProjectPanelHost
from manuskript.ui.plugins.editor_workspaces import EditorWorkspaceHost


class _CommandSignals(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(object)


class _CommandTask(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = _CommandSignals()

    def run(self):
        try:
            result = self.operation()
        except Exception as error:
            self.signals.failed.emit(error)
        else:
            self.signals.finished.emit(result)


class PluginUiController:
    """One window's plugin user interface.

    Window scope, despite the name: there is one of these per workspace
    window, and it owns that window's Plugins menu, its panels and
    workspaces, and the dialogs it opens. It used to describe itself as
    application-level, which was true only while there was one window.

    What is genuinely application scope arrives as the contribution
    service: the runtime, the option store, the media type registry, and
    the one announcement that the set of contributions changed. Every
    window subscribes to that and refreshes its own view; no window
    refreshes anybody else's, and none of them can miss the news.
    SHARED_SERVICES names what must be the same object in every window.

    The page type and markup profile services are deliberately per
    window: each reports errors to its own status bar and reads the
    document source from its own editor. They are views onto shared
    data, not copies of it.
    """

    #: Attributes that must be the same object in every window.
    SHARED_SERVICES = (
        "contributions", "runtime", "option_store", "mediaTypes",
    )

    def __init__(self, views, contributions, option_store=None,
                 media_types=None):
        self.views = views
        self.contributions = contributions
        self.runtime = contributions.runtime
        self.option_store = (
            option_store
            if option_store is not None
            else contributions.optionStore
        )
        self.mediaTypes = (
            media_types
            if media_types is not None
            else contributions.mediaTypes
        )
        # Every window refreshes its own view when the set of
        # contributions changes, rather than only the window whose
        # plugin manager happened to make the change.
        contributions.changed.connect(self.refresh_contributions)
        self.markupProfiles = MarkupProfileService(
            contributions.registry,
            report_error=views.show_status,
            parent=views.object_parent,
        )
        self.pageTypes = PageTypeService(
            contributions.registry,
            option_store=self.option_store,
            scope_grants=contributions,
            media_types=self.mediaTypes,
            report_error=views.show_status,
            source_provider=self._page_source,
            parent=views.object_parent,
        )
        self.manager = None

        views.tools_menu.addSeparator()
        self.menu = views.tools_menu.addMenu(
            views.translate("Plugins")
        )
        self.menu.setObjectName("menuPlugins")
        self.manageAction = QAction(
            views.translate("Manage Plugins…"),
            views.object_parent,
        )
        self.manageAction.setObjectName("actPlugins")
        self.manageAction.setStatusTip(
            views.translate("Manage installed Manuskript plugins")
        )
        self.menu.addAction(self.manageAction)
        self.manageAction.triggered.connect(self.show_manager)
        self.globalActions = (self.menu.menuAction(),)
        self.projectPanels = ProjectPanelHost(
            views.project_panels,
            self.runtime,
            menu=self.menu,
        )
        self.editorWorkspaces = EditorWorkspaceHost(
            views.editor_workspaces,
            self.runtime,
            menu=self.menu,
        )
        self._projectOpen = views.project_panels.project.is_open()
        self._commandActions = []
        self._commandTasks = set()
        self.refresh_commands()

    def _page_source(self, item):
        editor_host = self.views.editor_host()
        if editor_host is None:
            return item.text()
        current = editor_host.currentEditor()
        editors = [current] if current is not None else []
        editors.extend(
            editor
            for editor in editor_host.allAllTabs()
            if editor is not current
        )
        for editor in editors:
            index = getattr(editor, "currentIndex", None)
            if (
                index is not None
                and index.isValid()
                and index.internalPointer() is item
            ):
                source_editor = getattr(editor, "txtRedacText", None)
                if source_editor is not None:
                    return source_editor.toPlainText()
        return item.text()

    def attach_surface(self, instance):
        if self.editorWorkspaces is not None:
            self.editorWorkspaces.attach_surface(instance)

    def detach_surface(self, instance):
        if self.editorWorkspaces is not None:
            self.editorWorkspaces.detach_surface(instance)

    def show_manager(self):
        if self.manager is None:
            self.manager = PluginManagerDialog(
                self.contributions,
                self.views.dialog_parent,
                option_store=self.option_store,
                settings_context_provider=self._settings_context,
                media_types=self.mediaTypes,
            )
            self.manager.finished.connect(self._manager_closed)
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()

    def _settings_context(self, plugin_id):
        """Capabilities a plugin may use to configure itself.

        Nothing UI-shaped is built here. A panel that never asks for
        routing does not get a routing gateway, which is the difference
        between core offering a service and core imposing one.
        """
        return PluginSettingsContext(
            plugin_id=plugin_id,
            option_store=self.option_store,
            edit_options=partial(self._edit_options, plugin_id),
            show_status=self.views.show_status,
            capability=partial(self._settings_capability, plugin_id),
        )

    def _settings_capability(self, plugin_id, name):
        """Hand over a deferred service, if this plugin declared it.

        Same negotiation as during registration, enforced the same way:
        a name the manifest does not list is refused even when core has it.
        """
        if not self.runtime.declares(plugin_id, name):
            raise PluginScopeError(
                "Plugin {} did not declare capability {!r} in its "
                "manifest.".format(plugin_id, name)
            )
        builder = self._DEFERRED.get(name)
        if builder is None:
            raise PluginScopeError(
                "Capability {!r} is not available to a settings panel."
                .format(name)
            )
        return builder(self, plugin_id)

    def _export_routing(self, plugin_id):
        return ExportRoutingService(
            PageRoutingGateway(
                plugin_id,
                self.runtime.registry,
                self.pageTypes,
                export_routes_provider=self._export_routes,
                edit_options=partial(self._edit_options, plugin_id),
                show_status=self.views.show_status,
            )
        )

    def _media_registry(self, _plugin_id):
        return MediaTypeView(self.mediaTypes)

    #: Services the UI host builds, because they need a running
    #: application and a plugin to be scoped to.
    _DEFERRED = {
        CAPABILITY_UI_EXPORT_ROUTING: _export_routing,
        CAPABILITY_MEDIA_REGISTRY: _media_registry,
    }

    def _edit_options(self, plugin_id, contribution, parent=None):
        """Open the standard options editor for a plugin's own work."""
        owned = {
            record.id
            for record in self.runtime.registry.plugin_records(plugin_id)
        }
        if contribution.descriptor.id not in owned:
            raise PluginScopeError(
                "Plugin {} cannot configure {!r}, which it does not "
                "provide.".format(plugin_id, contribution.descriptor.id)
            )
        dialog = PluginOptionsDialog(
            contribution,
            self.option_store,
            parent if parent is not None else self.views.dialog_parent,
        )
        return dialog.exec()

    def _export_routes(self):
        from manuskript import exporter
        from manuskript.exporter.page_routes import (
            page_renderer_routes,
        )

        exporters = exporter.create_exporters(
            self.views.export_context(),
            plugin_runtime=self.runtime,
            plugin_option_store=self.option_store,
        )
        return page_renderer_routes(exporters)

    def _manager_closed(self, _result):
        if self.manager is not None:
            self.manager.deleteLater()
        self.manager = None

    def refresh_contributions(self):
        self._clear_commands()
        self.projectPanels.refresh()
        self.editorWorkspaces.refresh()
        self.markupProfiles.refresh()
        self.pageTypes.refresh()
        self.views.refresh_card_styles()
        self.refresh_commands()

    def refresh_commands(self):
        records = sorted(
            self.runtime.registry.records("command"),
            key=lambda record: record.contribution.descriptor.name.casefold(),
        )
        if not records:
            return
        separator = self.menu.addSeparator()
        self._commandActions.append(separator)
        for record in records:
            contribution = record.contribution
            action = QAction(
                contribution.descriptor.name,
                self.views.object_parent,
            )
            action.setObjectName(
                "pluginCommand." + contribution.descriptor.id
            )
            action.setStatusTip(contribution.descriptor.description)
            if contribution.shortcut:
                action.setShortcut(QKeySequence(contribution.shortcut))
            action.setEnabled(
                self._projectOpen or not contribution.project_required
            )
            action.triggered.connect(
                partial(self._invoke_command, contribution)
            )
            self.menu.addAction(action)
            self._commandActions.append(action)

    def _clear_commands(self):
        for action in self._commandActions:
            self.menu.removeAction(action)
            action.deleteLater()
        self._commandActions = []

    def _invoke_command(self, contribution, _checked=False):
        task = _CommandTask(contribution.invoke)
        self._commandTasks.add(task)

        def finished(result):
            self._commandTasks.discard(task)
            if self.views is not None and result:
                self.views.show_status(str(result))

        def failed(error):
            self._commandTasks.discard(task)
            if self.views is None:
                return
            self.views.show_status(
                self.views.translate("Plugin command failed.")
                + " {}: {}".format(type(error).__name__, error),
                importance=2,
            )

        task.signals.finished.connect(finished)
        task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def _update_command_scope(self):
        commands = {
            contribution.descriptor.id: contribution
            for contribution in self.runtime.registry.commands
        }
        for action in self._commandActions:
            name = action.objectName()
            if not name.startswith("pluginCommand."):
                continue
            contribution = commands.get(name[len("pluginCommand."):])
            if contribution is not None:
                action.setEnabled(
                    self._projectOpen or not contribution.project_required
                )

    def project_opened(self):
        self._projectOpen = True
        self._update_command_scope()
        self.projectPanels.project_opened()
        self.editorWorkspaces.project_opened()

    def prepare_project_close(self):
        self._projectOpen = False
        self._update_command_scope()
        self.editorWorkspaces.prepare_project_close()
        self.projectPanels.prepare_project_close()

    def dispose(self):
        """Release this window's plugin UI from application services."""
        contributions = self.contributions
        if contributions is None:
            return
        try:
            contributions.changed.disconnect(
                self.refresh_contributions
            )
        except (RuntimeError, TypeError):
            pass
        self.editorWorkspaces.prepare_project_close()
        self.projectPanels.prepare_project_close()
        self._clear_commands()
        manager = self.manager
        self.manager = None
        if manager is not None:
            manager.close()
            manager.deleteLater()
        self.markupProfiles = None
        self.pageTypes = None
        self.projectPanels = None
        self.editorWorkspaces = None
        self.menu = None
        self.manageAction = None
        self.globalActions = ()
        self.views = None
        self.contributions = None
