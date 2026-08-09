from functools import partial

from PyQt5.QtWidgets import QAction

from manuskript.media_types import MediaTypeView, core_registry
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
from manuskript.ui.plugins.project_panel_views import ProjectPanelViews
from manuskript.ui.plugins.editor_workspaces import EditorWorkspaceHost
from manuskript.ui.plugins.editor_workspace_views import (
    EditorWorkspaceViews,
)


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

    def __init__(self, window, contributions, option_store=None,
                 media_types=None):
        self.window = window
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
            report_error=window.statusPresenter.show,
            parent=window,
        )
        self.pageTypes = PageTypeService(
            contributions.registry,
            option_store=self.option_store,
            media_types=self.mediaTypes,
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
            ProjectPanelViews.for_window(window),
            self.runtime,
            menu=self.menu,
        )
        self.editorWorkspaces = EditorWorkspaceHost(
            EditorWorkspaceViews.for_window(window),
            self.runtime,
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
                self.contributions,
                self.window,
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
            show_status=self.window.statusPresenter.show,
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
                show_status=self.window.statusPresenter.show,
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
