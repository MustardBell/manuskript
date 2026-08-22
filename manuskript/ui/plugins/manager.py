import html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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

from manuskript.plugins.contracts import (
    ContributionKind,
    ContributionScope,
)
from manuskript.plugins.runtime import PluginStatus


class PluginManagerDialog(QDialog):
    """Inspect, trust, enable, disable, and diagnose application plugins.

    Changes the set of contributions through the contribution service
    rather than the runtime directly, so that every window hears about a
    plugin being enabled -- not only whichever window this dialog was
    opened from.
    """

    _SCOPE_GRANT_ROLE = Qt.UserRole + 1

    def __init__(
            self, contributions, parent=None, option_store=None,
            settings_context_provider=None, media_types=None):
        super().__init__(parent)
        self.contributions = contributions
        self.runtime = contributions.runtime
        self.option_store = (
            option_store
            if option_store is not None
            else contributions.optionStore
        )
        self.settingsContextProvider = settings_context_provider
        self.mediaTypes = (
            media_types
            if media_types is not None
            else contributions.mediaTypes
        )
        self.pluginPanels = {}
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
                    for root in self.runtime.roots
                )
            )
        )
        locations.setWordWrap(True)
        locations.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root_layout.addWidget(locations)

        self.splitter = QSplitter(self)
        root_layout.addWidget(self.splitter, 1)

        self.pluginList = QTreeWidget(self.splitter)
        self.pluginList.setMinimumWidth(360)
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
        self.declarationsGroup = QGroupBox(
            self.tr("Declared contributions"),
            self.detailsWidget,
        )
        declarations_layout = QVBoxLayout(self.declarationsGroup)
        self.declarationsHelp = QLabel(self.declarationsGroup)
        self.declarationsHelp.setWordWrap(True)
        declarations_layout.addWidget(self.declarationsHelp)
        self.declarationsTree = QTreeWidget(self.declarationsGroup)
        self.declarationsTree.setHeaderLabels([
            self.tr("Kind"),
            self.tr("Contribution"),
            self.tr("Requested reach"),
            self.tr("Effective reach"),
        ])
        self.declarationsTree.setRootIsDecorated(False)
        self.declarationsTree.setAlternatingRowColors(True)
        self.declarationsTree.setAccessibleName(
            self.tr("Declared plugin contributions and their reach")
        )
        self.declarationsTree.setAccessibleDescription(self.tr(
            "Inspect what the selected plugin contributes and grant or "
            "revoke optional reach beyond content it owns."
        ))
        declarations_layout.addWidget(self.declarationsTree)
        details_layout.addWidget(self.declarationsGroup)
        self.pluginSpace = QWidget(self.detailsWidget)
        self.pluginSpaceLayout = QVBoxLayout(self.pluginSpace)
        self.pluginSpaceLayout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(self.pluginSpace)
        details_layout.addStretch(1)
        self.detailsScroll.setWidget(self.detailsWidget)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes((380, 540))

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
        self.declarationsTree.itemChanged.connect(
            self._declaration_item_changed
        )
        self.refreshButton.clicked.connect(self.refresh)
        self.enableButton.clicked.connect(self.enable_selected)
        self.disableButton.clicked.connect(self.disable_selected)

        self.refresh()

    def refresh(self):
        selected_id = self.selected_plugin_id()
        self.contributions.rediscover()
        self._populate(selected_id)

    def selected_plugin_id(self):
        item = self.pluginList.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def enable_selected(self):
        plugin_id = self.selected_plugin_id()
        if plugin_id is None or not self._confirm_enable(plugin_id):
            return
        self.contributions.enable(plugin_id)
        self._populate(plugin_id)

    def disable_selected(self):
        plugin_id = self.selected_plugin_id()
        if plugin_id is None:
            return
        self.contributions.disable(plugin_id)
        self._populate(plugin_id)

    def _confirm_enable(self, plugin_id):
        record = self.runtime.records[plugin_id]
        result = QMessageBox.warning(
            self,
            self.tr("Trust this plugin?"),
            self.tr(
                "<p><b>Enable {name}?</b></p>"
                "<p>Manuskript plugins are programs. An enabled plugin "
                "may load in the application or start an external process, "
                "with the same access to your files and computer as "
                "Manuskript itself.</p>"
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
        # clear() and setCurrentItem() both emit currentItemChanged, which
        # would rebuild the plugin's panel widget several times per refresh.
        # Silence the list and refresh the details exactly once, at the end.
        previously_blocked = self.pluginList.blockSignals(True)
        try:
            self.pluginList.clear()
            selected_item = None
            for plugin_id, record in sorted(self.runtime.records.items()):
                status = self._status_text(record.status)
                if record.warning:
                    accessible_status = self.tr(
                        "{}; compatibility warning"
                    ).format(status)
                    status = self.tr("{} ⚠").format(status)
                else:
                    accessible_status = status
                item = QTreeWidgetItem(
                    [
                        record.manifest.name,
                        record.manifest.version,
                        status,
                    ]
                )
                item.setData(0, Qt.UserRole, plugin_id)
                item.setData(2, Qt.AccessibleTextRole, accessible_status)
                if record.error or record.warning:
                    item.setToolTip(2, record.error or record.warning)
                self.pluginList.addTopLevelItem(item)
                if plugin_id == selected_id:
                    selected_item = item

            self.pluginList.resizeColumnToContents(0)
            self.pluginList.resizeColumnToContents(1)
            self.pluginList.resizeColumnToContents(2)
            if (
                selected_item is None
                and self.pluginList.topLevelItemCount()
            ):
                selected_item = self.pluginList.topLevelItem(0)
            self.pluginList.setCurrentItem(selected_item)
        finally:
            self.pluginList.blockSignals(previously_blocked)
        self._discard_plugin_panels()
        self._show_discovery_issues()
        self._selection_changed(selected_item)

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
            self._show_declarations(None)
            self._show_plugin_panel(None)
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
            self.tr("Project formats: {}").format(
                html.escape(manifest.project_formats.label)
            ),
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
        overridden = self._overridden_media_types(manifest)
        if overridden:
            # Findable outside the developer tool on purpose: somebody who
            # remaps a format in March cannot otherwise explain a broken
            # export in July.
            metadata.append(self.tr(
                "<b>{} media type(s) this plugin declares are overridden: "
                "{}</b>"
            ).format(len(overridden), html.escape(", ".join(overridden))))
        self.metadataLabel.setText("<br>".join(metadata))
        if record.error:
            message = (
                "<b>{}</b><br>{}".format(
                    self.tr("Error"),
                    html.escape(record.error),
                )
            )
        elif record.warning:
            message = "<b>{}</b><br>{}".format(
                self.tr("Compatibility warning"),
                html.escape(record.warning),
            )
        else:
            message = ""
        self.errorLabel.setText(message)
        self._show_declarations(plugin_id)
        self._show_plugin_panel(plugin_id)
        self.enableButton.setEnabled(
            record.status is not PluginStatus.LOADED
        )
        self.disableButton.setEnabled(
            record.status is not PluginStatus.DISABLED
            or plugin_id in self.runtime.preferences.enabled_plugin_ids
        )

    def _show_declarations(self, plugin_id):
        """Show core-validated declarations separately from plugin settings."""

        tree = self.declarationsTree
        blocked = tree.blockSignals(True)
        try:
            tree.clear()
            records = (
                self.runtime.registry.plugin_records(plugin_id)
                if plugin_id is not None else ()
            )
            if not records:
                self.declarationsHelp.setText(self.tr(
                    "Enable this plugin to inspect its validated "
                    "contributions."
                ))
                tree.setVisible(False)
                self.declarationsGroup.setVisible(plugin_id is not None)
                return

            self.declarationsGroup.setVisible(True)
            tree.setVisible(True)
            self.declarationsHelp.setText(self.tr(
                "A declaration may request broader reach, but it remains "
                "limited to its own content until you allow that reach."
            ))
            for record in sorted(
                records,
                key=lambda value: (
                    value.kind.value,
                    value.contribution.descriptor.name.casefold(),
                ),
            ):
                contribution = record.contribution
                scope = getattr(contribution, "scope", None)
                requested = self.tr("—")
                effective = self.tr("—")
                if scope is ContributionScope.OWN:
                    requested = self.tr("Own pages")
                    effective = self.tr("Own pages")
                elif scope is ContributionScope.ALL:
                    requested = self.tr("All pages")
                    granted = self.contributions.scope_granted(
                        record.plugin_id,
                        record.kind,
                        record.id,
                        scope,
                    )
                    effective = (
                        self.tr("All pages")
                        if granted else self.tr("Own pages")
                    )

                item = QTreeWidgetItem([
                    record.kind.value.replace("_", " ").title(),
                    contribution.descriptor.name,
                    requested,
                    effective,
                ])
                item.setToolTip(1, contribution.descriptor.description)
                if scope is ContributionScope.ALL:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        3, Qt.Checked if granted else Qt.Unchecked
                    )
                    item.setData(3, self._SCOPE_GRANT_ROLE, (
                        record.plugin_id,
                        record.kind.value,
                        record.id,
                        scope.value,
                    ))
                    item.setToolTip(3, self.tr(
                        "Allow {} on documents not owned by this plugin."
                    ).format(contribution.descriptor.name))
                    item.setData(
                        3,
                        Qt.AccessibleTextRole,
                        self.tr("{}; {}")
                        .format(effective, item.toolTip(3)),
                    )
                tree.addTopLevelItem(item)
            for column in range(tree.columnCount()):
                tree.resizeColumnToContents(column)
        finally:
            tree.blockSignals(blocked)

    def _declaration_item_changed(self, item, column):
        if column != 3:
            return
        request = item.data(column, self._SCOPE_GRANT_ROLE)
        if not request:
            return
        plugin_id, kind, contribution_id, scope = request
        granted = item.checkState(column) == Qt.Checked
        try:
            self.contributions.set_scope_grant(
                plugin_id, kind, contribution_id, scope, granted
            )
        except (TypeError, ValueError) as error:
            blocked = self.declarationsTree.blockSignals(True)
            try:
                item.setCheckState(
                    column, Qt.Unchecked if granted else Qt.Checked
                )
            finally:
                self.declarationsTree.blockSignals(blocked)
            self.errorLabel.setText(
                "<b>{}</b><br>{}".format(
                    self.tr("Scope change failed"),
                    html.escape(str(error)),
                )
            )
            return
        effective = self.tr("All pages") if granted else self.tr("Own pages")
        item.setText(column, effective)
        item.setData(
            column,
            Qt.AccessibleTextRole,
            self.tr("{}; {}").format(effective, item.toolTip(column)),
        )

    def _show_plugin_panel(self, plugin_id):
        """Give the lower details pane to the selected plugin, or to no one.

        Manuskript draws nothing of its own here. A plugin that registers no
        settings panel simply gets empty space, which is why one plugin's
        configuration can never appear while another is selected.
        """
        for widget in self.pluginPanels.values():
            widget.setVisible(False)
        if plugin_id is None:
            self.pluginSpace.setVisible(False)
            return
        widget = self.pluginPanels.get(plugin_id)
        if widget is None:
            widget = self._build_plugin_panel(plugin_id)
            if widget is not None:
                self.pluginPanels[plugin_id] = widget
                self.pluginSpaceLayout.addWidget(widget)
        self.pluginSpace.setVisible(widget is not None)
        if widget is not None:
            widget.setVisible(True)

    def _build_plugin_panel(self, plugin_id):
        records = self.runtime.registry.plugin_records(
            plugin_id,
            ContributionKind.SETTINGS_PANEL,
        )
        if not records or self.settingsContextProvider is None:
            return None
        container = QWidget(self.pluginSpace)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        context = self.settingsContextProvider(plugin_id)
        for record in records:
            contribution = record.contribution
            group = QGroupBox(contribution.descriptor.name, container)
            group_layout = QVBoxLayout(group)
            try:
                if contribution.widget_factory is not None:
                    widget = contribution.widget_factory(context, group)
                else:
                    from manuskript.ui.plugins.declarative_ui import (
                        build_static_ui_widget,
                    )
                    widget = build_static_ui_widget(
                        contribution.ui, group
                    )
                if not isinstance(widget, QWidget):
                    raise TypeError(
                        "Plugin settings factories must return QWidget "
                        "instances."
                    )
            except Exception as error:
                # A broken panel must not take the manager down with it.
                failure = QLabel(
                    self.tr("This plugin's settings failed to load.")
                    + "\n{}: {}".format(type(error).__name__, error),
                    group,
                )
                failure.setWordWrap(True)
                group_layout.addWidget(failure)
            else:
                group_layout.addWidget(widget)
            layout.addWidget(group)
        return container

    def _discard_plugin_panels(self):
        """Drop cached panels so enable/disable rebuilds them from scratch."""
        for widget in self.pluginPanels.values():
            self.pluginSpaceLayout.removeWidget(widget)
            widget.setParent(None)
            widget.deleteLater()
        self.pluginPanels = {}

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

    def _overridden_media_types(self, manifest):
        """Formats this plugin declared that the user has remapped."""
        if self.mediaTypes is None:
            return ()
        return tuple(
            media_id
            for media_id in manifest.declared_media_type_ids
            if self.mediaTypes.override(media_id)
        )

    def _status_text(self, status):
        return {
            PluginStatus.DISABLED: self.tr("Disabled"),
            PluginStatus.LOADED: self.tr("Enabled"),
            PluginStatus.INCOMPATIBLE: self.tr("Incompatible"),
            PluginStatus.UNSATISFIED: self.tr("Unsatisfied"),
            PluginStatus.FAILED: self.tr("Failed"),
        }[status]
