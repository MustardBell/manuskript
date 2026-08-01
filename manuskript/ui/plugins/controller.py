from PyQt5.QtWidgets import QAction

from manuskript.ui.plugins.manager import PluginManagerDialog
from manuskript.ui.plugins.markup_profiles import MarkupProfileService
from manuskript.ui.plugins.page_types import PageTypeService
from manuskript.ui.plugins.project_panels import ProjectPanelHost


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
                page_types=self.pageTypes,
                export_routes_provider=self._export_routes,
            )
            self.manager.finished.connect(self._manager_closed)
            self.manager.pluginsChanged.connect(
                self.refresh_contributions
            )
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()

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
        self.markupProfiles.refresh()
        self.pageTypes.refresh()

    def project_opened(self):
        self.projectPanels.project_opened()

    def prepare_project_close(self):
        self.projectPanels.prepare_project_close()
