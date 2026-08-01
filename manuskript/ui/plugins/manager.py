import html

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from manuskript.plugins.registry import ContributionKind
from manuskript.plugins.runtime import PluginStatus
from manuskript.ui.plugins.options import plugin_options_widget


class PluginManagerDialog(QDialog):
    """Inspect, trust, enable, disable, and diagnose application plugins."""

    pluginsChanged = pyqtSignal()

    def __init__(
            self, runtime, parent=None, option_store=None,
            page_types=None, export_routes_provider=None):
        super().__init__(parent)
        self.runtime = runtime
        self.option_store = option_store
        self.pageTypes = page_types
        self.exportRoutesProvider = export_routes_provider
        self._exportRoutes = ()
        self._syncingRendererRoute = False
        self.setWindowTitle(self.tr("Manage Plugins"))
        self.resize(960, 700)
        self.setMinimumSize(720, 520)

        root_layout = QVBoxLayout(self)
        introduction = QLabel(
            self.tr(
                "Plugins extend Manuskript with importers, exporters, "
                "project tools, export conversion stages, and markup "
                "behavior."
            )
        )
        introduction.setWordWrap(True)
        root_layout.addWidget(introduction)
        locations = QLabel(
            self.tr(
                "Plugin subdirectories containing "
                "<code>plugin.json</code> are discovered under:<br>"
                "<code>{}</code><br><br>"
                "Python files directly in that directory implement "
                "the plugin host API and are not plugins themselves."
            ).format(
                "<br>".join(
                    html.escape(str(root))
                    for root in runtime.roots
                )
            )
        )
        locations.setWordWrap(True)
        locations.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root_layout.addWidget(locations)

        self.splitter = QSplitter(self)
        root_layout.addWidget(self.splitter, 1)

        self.pluginList = QTreeWidget(self.splitter)
        self.pluginList.setMinimumWidth(280)
        self.pluginList.setHeaderLabels(
            [
                self.tr("Plugin"),
                self.tr("Version"),
                self.tr("Status"),
            ]
        )
        self.pluginList.setRootIsDecorated(False)
        self.pluginList.setAlternatingRowColors(True)

        self.detailsScroll = QScrollArea(self.splitter)
        self.detailsScroll.setWidgetResizable(True)
        self.detailsScroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.detailsWidget = QWidget()
        details_layout = QVBoxLayout(self.detailsWidget)
        details_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.nameLabel = QLabel()
        self.nameLabel.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addWidget(self.nameLabel)
        self.descriptionLabel = QLabel()
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        details_layout.addWidget(self.descriptionLabel)
        self.metadataLabel = QLabel()
        self.metadataLabel.setWordWrap(True)
        self.metadataLabel.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        details_layout.addWidget(self.metadataLabel)
        self.errorLabel = QLabel()
        self.errorLabel.setWordWrap(True)
        self.errorLabel.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        details_layout.addWidget(self.errorLabel)
        self.rendererGroup = self._build_renderer_group(
            self.detailsWidget
        )
        details_layout.addWidget(self.rendererGroup)
        details_layout.addStretch(1)
        self.detailsScroll.setWidget(self.detailsWidget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes((300, 620))

        action_layout = QHBoxLayout()
        self.refreshButton = QPushButton(self.tr("Refresh"))
        self.enableButton = QPushButton(self.tr("Enable"))
        self.disableButton = QPushButton(self.tr("Disable"))
        action_layout.addWidget(self.refreshButton)
        action_layout.addStretch(1)
        action_layout.addWidget(self.enableButton)
        action_layout.addWidget(self.disableButton)
        root_layout.addLayout(action_layout)

        self.discoveryLabel = QLabel()
        self.discoveryLabel.setWordWrap(True)
        self.discoveryLabel.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        root_layout.addWidget(self.discoveryLabel)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        root_layout.addWidget(buttons)

        self.pluginList.currentItemChanged.connect(
            self._selection_changed
        )
        self.refreshButton.clicked.connect(self.refresh)
        self.enableButton.clicked.connect(self.enable_selected)
        self.disableButton.clicked.connect(self.disable_selected)

        self.refresh()

    def _build_renderer_group(self, parent):
        group = QGroupBox(self.tr("Page renderer routing"), parent)
        form = QFormLayout(group)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.pageTypeCombo = QComboBox(group)
        self.renderTargetCombo = QComboBox(group)
        self.pageRendererCombo = QComboBox(group)
        self.configureRendererButton = QPushButton(
            self.tr("Configure renderer…"),
            group,
        )
        self.rendererInfoLabel = QLabel(group)
        self.rendererInfoLabel.setWordWrap(True)
        form.addRow(self.tr("Page type"), self.pageTypeCombo)
        form.addRow(self.tr("Export format"), self.renderTargetCombo)
        form.addRow(self.tr("Renderer"), self.pageRendererCombo)
        form.addRow("", self.configureRendererButton)
        form.addRow("", self.rendererInfoLabel)
        self.pageTypeCombo.currentIndexChanged.connect(
            self._page_type_route_changed
        )
        self.renderTargetCombo.currentIndexChanged.connect(
            self._renderer_target_changed
        )
        self.pageRendererCombo.currentIndexChanged.connect(
            self._renderer_route_changed
        )
        self.configureRendererButton.clicked.connect(
            self._configure_renderer
        )
        return group

    def refresh(self):
        selected_id = self.selected_plugin_id()
        self.runtime.discover()
        self.runtime.load_enabled()
        self._populate(selected_id)
        self.pluginsChanged.emit()

    def selected_plugin_id(self):
        item = self.pluginList.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def enable_selected(self):
        plugin_id = self.selected_plugin_id()
        if plugin_id is None or not self._confirm_enable(plugin_id):
            return
        self.runtime.enable(plugin_id)
        self._populate(plugin_id)
        self.pluginsChanged.emit()

    def disable_selected(self):
        plugin_id = self.selected_plugin_id()
        if plugin_id is None:
            return
        self.runtime.disable(plugin_id)
        self._populate(plugin_id)
        self.pluginsChanged.emit()

    def _confirm_enable(self, plugin_id):
        record = self.runtime.records[plugin_id]
        result = QMessageBox.warning(
            self,
            self.tr("Trust this plugin?"),
            self.tr(
                "<p><b>Enable {name}?</b></p>"
                "<p>Manuskript plugins are Python programs. An enabled "
                "plugin runs with the same access to your files and "
                "computer as Manuskript itself.</p>"
                "<p>Only enable plugins whose source and publisher you "
                "trust.</p>"
                "<p><code>{path}</code></p>"
            ).format(
                name=html.escape(record.manifest.name),
                path=html.escape(str(record.manifest.root)),
            ),
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return result == QMessageBox.Yes

    def _populate(self, selected_id=None):
        self.pluginList.clear()
        selected_item = None
        for plugin_id, record in sorted(self.runtime.records.items()):
            item = QTreeWidgetItem(
                [
                    record.manifest.name,
                    record.manifest.version,
                    self._status_text(record.status),
                ]
            )
            item.setData(0, Qt.UserRole, plugin_id)
            if record.error:
                item.setToolTip(2, record.error)
            self.pluginList.addTopLevelItem(item)
            if plugin_id == selected_id:
                selected_item = item

        self.pluginList.resizeColumnToContents(0)
        self.pluginList.resizeColumnToContents(1)
        if selected_item is None and self.pluginList.topLevelItemCount():
            selected_item = self.pluginList.topLevelItem(0)
        self.pluginList.setCurrentItem(selected_item)
        self._show_discovery_issues()
        self._selection_changed(selected_item)
        self._populate_renderer_routes()

    def _populate_renderer_routes(self):
        self._exportRoutes = (
            tuple(self.exportRoutesProvider())
            if self.exportRoutesProvider is not None
            else ()
        )
        available = (
            self.pageTypes is not None
            and self.option_store is not None
            and bool(self.runtime.registry.page_types)
            and bool(self.runtime.registry.page_renderers)
            and bool(self._exportRoutes)
        )
        self.rendererGroup.setVisible(available)
        if not available:
            return
        selected_page = self.pageTypeCombo.currentData()
        self._syncingRendererRoute = True
        try:
            self.pageTypeCombo.clear()
            for contribution in sorted(
                    self.runtime.registry.page_types,
                    key=lambda value: value.descriptor.name):
                self.pageTypeCombo.addItem(
                    contribution.descriptor.name,
                    contribution.descriptor.id,
                )
            index = self.pageTypeCombo.findData(selected_page)
            self.pageTypeCombo.setCurrentIndex(max(0, index))
            self._populate_render_targets()
        finally:
            self._syncingRendererRoute = False
        self._populate_renderer_choices()

    def _populate_render_targets(self):
        selected = self.renderTargetCombo.currentData()
        self.renderTargetCombo.clear()
        duplicate_labels = {
            route.label
            for route in self._exportRoutes
            if sum(
                other.label == route.label
                for other in self._exportRoutes
            ) > 1
        }
        for route in self._exportRoutes:
            label = route.label
            if route.label in duplicate_labels:
                label = "{} — {}".format(label, route.exporter_name)
            self.renderTargetCombo.addItem(
                self.tr(label),
                route.id,
            )
        index = self.renderTargetCombo.findData(selected)
        self.renderTargetCombo.setCurrentIndex(max(0, index))

    def _populate_renderer_choices(self):
        if self._syncingRendererRoute or self.pageTypes is None:
            return
        page_type_id = self.pageTypeCombo.currentData()
        route = self._selected_export_route()
        if route is None:
            self.pageRendererCombo.clear()
            self._update_renderer_details()
            return
        representation_format = route.representation_format
        self._syncingRendererRoute = True
        try:
            self.pageRendererCombo.clear()
            candidates = self.pageTypes.renderers_for(
                page_type_id,
                representation_format,
            )
            owners = {
                record.id: record.plugin_id
                for record in self.runtime.registry.records(
                    ContributionKind.PAGE_RENDERER
                )
            }
            for renderer in candidates:
                fallback = (
                    representation_format
                    not in renderer.target_formats
                )
                label = renderer.descriptor.name
                if fallback:
                    label += self.tr(" (compatible fallback)")
                owner = owners.get(renderer.descriptor.id)
                if owner:
                    label += " — " + owner
                self.pageRendererCombo.addItem(
                    label,
                    renderer.descriptor.id,
                )
            selected = self.pageTypes.selected_renderer_id(
                page_type_id,
                route.id,
            )
            index = self.pageRendererCombo.findData(selected)
            self.pageRendererCombo.setCurrentIndex(max(0, index))
        finally:
            self._syncingRendererRoute = False
        self._update_renderer_details()

    def _page_type_route_changed(self, _index):
        if self._syncingRendererRoute:
            return
        self._syncingRendererRoute = True
        try:
            self._populate_render_targets()
        finally:
            self._syncingRendererRoute = False
        self._populate_renderer_choices()

    def _renderer_target_changed(self, _index):
        if not self._syncingRendererRoute:
            self._populate_renderer_choices()

    def _renderer_route_changed(self, _index):
        if self._syncingRendererRoute or self.pageTypes is None:
            return
        renderer_id = self.pageRendererCombo.currentData()
        if renderer_id:
            route = self._selected_export_route()
            if route is None:
                return
            self.pageTypes.select_renderer(
                self.pageTypeCombo.currentData(),
                route.id,
                renderer_id,
                representation_format=route.representation_format,
            )
        self._update_renderer_details()

    def _selected_export_route(self):
        route_id = self.renderTargetCombo.currentData()
        return next((
            route
            for route in self._exportRoutes
            if route.id == route_id
        ), None)

    def _selected_renderer(self):
        renderer_id = self.pageRendererCombo.currentData()
        return next((
            renderer
            for renderer in self.runtime.registry.page_renderers
            if renderer.descriptor.id == renderer_id
        ), None)

    def _update_renderer_details(self):
        renderer = self._selected_renderer()
        if renderer is None:
            self.rendererInfoLabel.setText(
                self.tr("No renderer is available for this route.")
            )
            self.configureRendererButton.setEnabled(False)
            return
        self.rendererInfoLabel.setText(renderer.descriptor.description)
        self.configureRendererButton.setEnabled(bool(
            renderer.options or renderer.options_view_factory
        ))

    def _configure_renderer(self):
        renderer = self._selected_renderer()
        if renderer is None or self.option_store is None:
            return
        dialog = PageRendererOptionsDialog(
            renderer,
            self.option_store,
            self,
        )
        dialog.exec()

    def _selection_changed(self, item, _previous=None):
        plugin_id = (
            item.data(0, Qt.UserRole)
            if item is not None
            else None
        )
        record = self.runtime.records.get(plugin_id)
        if record is None:
            self.nameLabel.clear()
            self.descriptionLabel.clear()
            self.metadataLabel.clear()
            self.errorLabel.clear()
            self.enableButton.setEnabled(False)
            self.disableButton.setEnabled(False)
            return

        manifest = record.manifest
        self.nameLabel.setText(
            "<b>{}</b> <code>{}</code>".format(
                html.escape(manifest.name),
                html.escape(manifest.id),
            )
        )
        self.descriptionLabel.setTextFormat(Qt.PlainText)
        self.descriptionLabel.setText(manifest.description)
        metadata = [
            self.tr("Version: {}").format(
                html.escape(manifest.version)
            ),
            self.tr("API: {}").format(manifest.api_version),
        ]
        metadata.append(self.tr("Installed plugin"))
        if manifest.author:
            metadata.append(
                self.tr("Author: {}").format(
                    html.escape(manifest.author)
                )
            )
        if manifest.homepage:
            metadata.append(
                self.tr("Homepage: {}").format(
                    html.escape(manifest.homepage)
                )
            )
        metadata.append(
            self.tr("Location: {}").format(
                html.escape(str(manifest.root))
            )
        )
        self.metadataLabel.setText("<br>".join(metadata))
        self.errorLabel.setText(
            (
                "<b>{}</b><br>{}".format(
                    self.tr("Error"),
                    html.escape(record.error),
                )
                if record.error
                else ""
            )
        )
        self.enableButton.setEnabled(
            record.status is not PluginStatus.LOADED
        )
        self.disableButton.setEnabled(
            record.status is not PluginStatus.DISABLED
            or plugin_id in self.runtime.preferences.enabled_plugin_ids
        )

    def _show_discovery_issues(self):
        issues = self.runtime.discovery_issues
        if not issues:
            self.discoveryLabel.clear()
            return
        self.discoveryLabel.setText(
            "<b>{}</b><br>{}".format(
                self.tr("Discovery problems"),
                "<br>".join(
                    "{}: {}".format(
                        html.escape(issue.path),
                        html.escape(issue.error),
                    )
                    for issue in issues
                ),
            )
        )

    def _status_text(self, status):
        return {
            PluginStatus.DISABLED: self.tr("Disabled"),
            PluginStatus.LOADED: self.tr("Enabled"),
            PluginStatus.INCOMPATIBLE: self.tr("Incompatible"),
            PluginStatus.FAILED: self.tr("Failed"),
        }[status]


class PageRendererOptionsDialog(QDialog):
    def __init__(self, contribution, option_store, parent=None):
        super().__init__(parent)
        self.contribution = contribution
        self.option_store = option_store
        self.setWindowTitle(
            self.tr("Configure {}")
            .format(contribution.descriptor.name)
        )
        self.resize(760, 650)
        layout = QVBoxLayout(self)
        description = QLabel(contribution.descriptor.description, self)
        description.setWordWrap(True)
        layout.addWidget(description)
        self.optionsWidget = plugin_options_widget(
            contribution,
            option_store,
            None,
        )
        self.optionsScroll = QScrollArea(self)
        self.optionsScroll.setWidgetResizable(True)
        self.optionsScroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.optionsScroll.setWidget(self.optionsWidget)
        layout.addWidget(self.optionsScroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self.option_store.save(
            self.contribution.descriptor.id,
            self.optionsWidget.values(),
        )
        self.accept()
