from functools import partial

from PyQt5.QtWidgets import QAction

from manuskript.plugins.api import PluginSettingsContext
from manuskript.plugins.errors import PluginScopeError
from manuskript.ui.plugins.manager import PluginManagerDialog
from manuskript.ui.plugins.options import PluginOptionsDialog
from manuskript.ui.plugins.markup_profiles import MarkupProfileService
from manuskript.ui.plugins.page_routing import PageRoutingGateway
from manuskript.ui.plugins.page_types import PageTypeService
from manuskript.ui.plugins.project_panels import ProjectPanelHost
from manuskript.ui.plugins.editor_workspaces import EditorWorkspaceHost


class PluginUiController:
    """Own application-level plugin UI and contribution refreshes."""

    def __init__(self, window, runtime, option_store):
        self.window = window
        self.runtime = runtime
        self.option_store = option_store
        self.markupProfiles = MarkupProfileService(
            runtime.registry,
            report_error=window.statusPresenter.show,
            parent=window,
        )
        self.pageTypes = PageTypeService(
            runtime.registry,
            option_store=option_store,
            report_error=window.statusPresenter.show,
            source_provider=self._page_source,
            parent=window,
        )
        self.manager = None

        window.menuTools.addSeparator()
        self.menu = window.menuTools.addMenu(window.tr("Plugins"))
        self.menu.setObjectName("menuPlugins")
        self.manageAction = QAction(
            window.tr("Manage Plugins…"),
            window,
        )
        self.manageAction.setObjectName("actPlugins")
        self.manageAction.setStatusTip(
            window.tr("Manage installed Manuskript plugins")
        )
        self.menu.addAction(self.manageAction)
        self.manageAction.triggered.connect(self.show_manager)
        self.globalActions = (self.menu.menuAction(),)
        self.projectPanels = ProjectPanelHost(
            window,
            runtime,
            menu=self.menu,
        )
        self.editorWorkspaces = EditorWorkspaceHost(
            window,
            runtime,
            menu=self.menu,
        )

    def _page_source(self, item):
        current = self.window.mainEditor.currentEditor()
        editors = [current] if current is not None else []
        editors.extend(
            editor
            for editor in self.window.mainEditor.allAllTabs()
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

    def show_manager(self):
        if self.manager is None:
            self.manager = PluginManagerDialog(
                self.runtime,
                self.window,
                option_store=self.option_store,
                settings_context_provider=self._settings_context,
            )
            self.manager.finished.connect(self._manager_closed)
            self.manager.pluginsChanged.connect(
                self.refresh_contributions
            )
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()

    def _settings_context(self, plugin_id):
        """Capabilities a plugin may use to configure itself."""
        return PluginSettingsContext(
            plugin_id=plugin_id,
            page_routing=PageRoutingGateway(
                plugin_id,
                self.runtime.registry,
                self.pageTypes,
                export_routes_provider=self._export_routes,
            ),
            option_store=self.option_store,
            edit_options=partial(self._edit_options, plugin_id),
            show_status=self.window.statusPresenter.show,
        )

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
            parent if parent is not None else self.window,
        )
        return dialog.exec()

    def _export_routes(self):
        from manuskript import exporter
        from manuskript.exporter.page_routes import (
            page_renderer_routes,
        )

        exporters = exporter.create_exporters(
            self.window.exportContext(),
            plugin_runtime=self.runtime,
            plugin_option_store=self.option_store,
        )
        return page_renderer_routes(exporters)

    def _manager_closed(self, _result):
        if self.manager is not None:
            self.manager.deleteLater()
        self.manager = None

    def refresh_contributions(self):
        self.projectPanels.refresh()
        self.editorWorkspaces.refresh()
        self.markupProfiles.refresh()
        self.pageTypes.refresh()
        cardStyles = getattr(self.window, "cardStyles", None)
        if cardStyles is not None:
            cardStyles.refresh()

    def project_opened(self):
        self.projectPanels.project_opened()
        self.editorWorkspaces.project_opened()

    def prepare_project_close(self):
        self.editorWorkspaces.prepare_project_close()
        self.projectPanels.prepare_project_close()
