import logging
import os

from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from manuskript.exporter.basic import basicExporter, basicFormat
from manuskript.exporter.page_routes import page_renderer_route_id
from manuskript.plugins.execution import run_conversion, run_export
from manuskript.plugins.snapshot import (
    project_snapshot_from_export_context,
)
from manuskript.ui.plugins.options import plugin_options_widget


LOGGER = logging.getLogger(__name__)


class ArtifactExportFormat(basicFormat):
    """Compile UI adapter for formats that produce in-memory artifacts."""

    implemented = True
    requires = {
        "Settings": True,
        "Preview": True,
    }
    file_extensions = ()
    error_title = "Export failed"

    def previewWidget(self):
        widget = QPlainTextEdit()
        widget.setFrameShape(QFrame.NoFrame)
        widget.setReadOnly(True)
        return widget

    def preview(self, settingsWidget, previewWidget):
        try:
            artifact = self.artifact(settingsWidget)
            self._show_warnings(artifact)
            if isinstance(artifact.content, bytes):
                previewWidget.setPlainText(
                    self.tr("Binary output: {} bytes ({})").format(
                        len(artifact.content),
                        artifact.media_type,
                    )
                )
            else:
                previewWidget.setPlainText(artifact.content)
        except Exception as error:
            self._show_error(settingsWidget, error)

    def export(self, settingsWidget):
        try:
            artifact = self.artifact(settingsWidget)
            self._show_warnings(artifact)
            filename, _selected = QFileDialog.getSaveFileName(
                settingsWidget,
                self.tr("Export with {}").format(self.name),
                os.path.join(
                    self.context.project_path,
                    artifact.suggested_name,
                ),
                self._file_filter(),
            )
            if not filename:
                return
            if isinstance(artifact.content, bytes):
                with open(filename, "wb") as output:
                    output.write(artifact.content)
            else:
                with open(
                    filename,
                    "wt",
                    encoding="utf-8",
                    newline="\n",
                ) as output:
                    output.write(artifact.content)
        except Exception as error:
            self._show_error(settingsWidget, error)

    def _file_filter(self):
        if not self.file_extensions:
            return self.tr("All files (*)")
        patterns = " ".join(
            "*{}".format(
                extension
                if extension.startswith(".")
                else "." + extension
            )
            for extension in self.file_extensions
        )
        return "{} ({})".format(self.name, patterns)

    def _show_error(self, parent, error):
        QMessageBox.critical(
            parent,
            self.tr(self.error_title),
            "{}\n\n{}".format(self.name, error),
        )

    def _show_warnings(self, artifact):
        warnings = tuple(getattr(artifact, "warnings", ()))
        if not warnings:
            return
        message = "; ".join(warnings)
        LOGGER.warning("%s: %s", self.name, message)
        presenter = getattr(self.context.parent, "statusPresenter", None)
        if presenter is not None:
            presenter.show(message)


class PluginExportFormat(ArtifactExportFormat):
    error_title = "Plugin export failed"

    def __init__(self, contribution, context, option_store):
        descriptor = contribution.descriptor
        super().__init__(
            name=descriptor.name,
            description=descriptor.description,
            icon=descriptor.icon,
            context=context,
        )
        self.contribution = contribution
        self.option_store = option_store
        self.format_id = contribution.output_format
        self.file_extensions = descriptor.extensions

    def settingsWidget(self):
        return plugin_options_widget(
            self.contribution,
            self.option_store,
        )

    def artifact(self, settings_widget):
        values = settings_widget.values()
        self.option_store.save(
            self.contribution.descriptor.id,
            values,
        )
        return run_export(
            self.contribution,
            project_snapshot_from_export_context(self.context),
            values,
        )


class ConversionExportSettings(QWidget):
    """Compose source compilation settings with converter options."""

    def __init__(
            self,
            source_format,
            contribution,
            option_store,
            parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        source_group = QGroupBox(
            self.tr("Compile source as {}").format(
                source_format.name
            ),
            self,
        )
        source_layout = QVBoxLayout(source_group)
        self.sourceSettings = source_format.settingsWidget()
        source_layout.addWidget(self.sourceSettings)
        layout.addWidget(source_group)

        self.converterSettings = plugin_options_widget(
            contribution,
            option_store,
            self,
        )
        if contribution.options or contribution.options_view_factory:
            converter_group = QGroupBox(
                self.tr("Conversion options"),
                self,
            )
            converter_layout = QVBoxLayout(converter_group)
            converter_layout.addWidget(self.converterSettings)
            layout.addWidget(converter_group)


class PluginConversionExportFormat(ArtifactExportFormat):
    """A Compile target backed by a source producer and plugin converter."""

    error_title = "Plugin conversion failed"

    def __init__(
            self,
            contribution,
            source_format,
            target_format,
            context,
            option_store,
            disambiguate=False):
        descriptor = contribution.descriptor
        name = descriptor.name
        if len(contribution.target_formats) > 1:
            name = "{} → {}".format(name, target_format)
        if disambiguate:
            name = "{} (from {})".format(name, source_format.name)
        super().__init__(
            name=name,
            description=descriptor.description,
            icon=descriptor.icon or source_format.icon,
            context=context,
        )
        self.contribution = contribution
        self.source_format = source_format
        self.source_format_id = source_format.format_id
        self.format_id = target_format
        self.target_format = target_format
        self.option_store = option_store
        self.file_extensions = (
            descriptor.extensions or ("." + target_format,)
        )

    def isValid(self):
        return self.source_format.isValid()

    def settingsWidget(self):
        return ConversionExportSettings(
            self.source_format,
            self.contribution,
            self.option_store,
        )

    def pageRenderTarget(self):
        operation = getattr(
            self.source_format,
            "pageRenderTarget",
            None,
        )
        return operation() if callable(operation) else ""

    def pageOutputFormat(self):
        return self.target_format

    def pageRendererRoute(self):
        representation = self.pageRenderTarget()
        if not representation:
            return ""
        return page_renderer_route_id(
            self.pageOutputFormat(),
            representation,
        )

    def artifact(self, settings_widget):
        route = self.pageRendererRoute()
        marker = object()
        previous = getattr(
            self.source_format,
            "_page_renderer_route_override",
            marker,
        )
        if route:
            self.source_format._page_renderer_route_override = route
        try:
            source = self.source_format.artifact(
                settings_widget.sourceSettings
            )
        finally:
            if previous is marker:
                self.source_format.__dict__.pop(
                    "_page_renderer_route_override",
                    None,
                )
            else:
                self.source_format._page_renderer_route_override = (
                    previous
                )
        values = settings_widget.converterSettings.values()
        self.option_store.save(
            self.contribution.descriptor.id,
            values,
        )
        return run_conversion(
            self.contribution,
            source.content,
            self.source_format_id,
            self.target_format,
            values,
        )


class PluginExporterGroup(basicExporter):
    def __init__(self, name, description, formats, context):
        super().__init__(context)
        self.name = name
        self.description = description
        self.exportTo = list(formats)

    def isValid(self):
        return True


def _artifact_sources(exporters):
    return [
        output_format
        for exporter in exporters
        for output_format in exporter.exportTo
        if getattr(output_format, "format_id", None)
        and callable(getattr(output_format, "artifact", None))
    ]


def create_plugin_exporters(
        context,
        runtime,
        option_store,
        source_exporters=()):
    if runtime is None:
        return []

    formats_by_plugin = {}
    direct_formats = []
    for record in runtime.registry.records("exporter"):
        output_format = PluginExportFormat(
            record.contribution,
            context,
            option_store,
        )
        formats_by_plugin.setdefault(record.plugin_id, []).append(
            output_format
        )
        direct_formats.append(output_format)

    producers = _artifact_sources(source_exporters) + direct_formats
    for record in runtime.registry.records("converter"):
        contribution = record.contribution
        sources = [
            producer
            for producer in producers
            if producer.format_id in contribution.source_formats
        ]
        route_count = len(sources) * len(contribution.target_formats)
        for source in sources:
            for target in contribution.target_formats:
                formats_by_plugin.setdefault(record.plugin_id, []).append(
                    PluginConversionExportFormat(
                        contribution,
                        source,
                        target,
                        context,
                        option_store,
                        disambiguate=route_count > 1,
                    )
                )

    exporters = []
    for plugin_id, formats in formats_by_plugin.items():
        plugin = runtime.records.get(plugin_id)
        name = plugin.manifest.name if plugin is not None else plugin_id
        description = (
            plugin.manifest.description if plugin is not None else ""
        )
        exporters.append(
            PluginExporterGroup(
                name,
                description,
                formats,
                context,
            )
        )
    return exporters
