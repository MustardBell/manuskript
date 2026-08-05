from unittest.mock import MagicMock

from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QWidget

from manuskript.exporter.basic import basicExporter, basicFormat
from manuskript.enums import Outline
from manuskript.models import outlineItem, outlineModel
from manuskript.models.outline_settings import DefaultOutlineSettings
from manuskript.plugins.api import (
    ConversionArtifact,
    ConversionContribution,
    ExportArtifact,
    ExportContribution,
    ExtensionDescriptor,
    ImportContribution,
    ImportNode,
    ImportResult,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.plugin_options import (
    InMemoryPluginOptionStore,
)
from manuskript.ui.plugins.export_adapter import (
    PluginConversionExportFormat,
    PluginExportFormat,
    create_plugin_exporters,
)
from manuskript.ui.plugins.import_adapter import PluginImporterAdapter
from manuskript.media_types import BBCODE, MARKDOWN


def test_plugin_export_adapter_builds_immutable_project_snapshot(
        tmp_path):
    captured = {}

    class Engine:
        def export(self, snapshot, options):
            captured["snapshot"] = snapshot
            return ExportArtifact(
                "<book>{}</book>".format(
                    snapshot.outline.children[0].text
                ),
                "book.fb2",
                "application/fb2+xml",
            )

    settings = DefaultOutlineSettings()
    model = outlineModel(settings=settings)
    scene = outlineItem(
        title="Opening",
        _type="md",
        settings=settings,
    )
    scene.setData(Outline.text, "Once")
    model.appendItem(scene)
    flat_data = QStandardItemModel(1, 8)
    flat_data.setData(flat_data.index(0, 0), "Novel")
    context = MagicMock()
    context.project_file = str(tmp_path / "book.msk")
    context.project_path = str(tmp_path)
    context.outline_model = model
    context.flat_data_model = flat_data
    contribution = ExportContribution(
        ExtensionDescriptor("example.fb2", "FB2"),
        Engine,
    )
    adapter = PluginExportFormat(
        contribution,
        context,
        InMemoryPluginOptionStore(),
    )

    artifact = adapter.artifact(adapter.settingsWidget())

    assert artifact.content == "<book>Once</book>"
    assert captured["snapshot"].metadata["title"] == "Novel"


def test_plugin_import_adapter_creates_outline_items():
    class Engine:
        def import_document(self, source, options):
            return ImportResult((
                ImportNode(
                    "Thread",
                    kind="folder",
                    children=(
                        ImportNode("Post", text="Hello"),
                    ),
                ),
            ))

    adapter = PluginImporterAdapter(
        ImportContribution(
            ExtensionDescriptor("example.outline", "Structured outline"),
            Engine,
            "Structured outlines (*.outline)",
        ),
        InMemoryPluginOptionStore(),
    )
    root = outlineItem(title="Root")

    items = adapter.startImport("document.outline", root, MagicMock())

    assert [item.title() for item in items] == ["Thread", "Post"]
    assert root.child(0).child(0).data(Outline.text) == "Hello"


def test_plugin_converter_is_a_compile_target_not_a_text_workbench(
        tmp_path):
    captured = {}

    class SourceSettings(QWidget):
        def writeSettings(self):
            pass

    class MarkdownSource(basicFormat):
        name = "Markdown"
        implemented = True
        media_type = MARKDOWN
        in_memory = True

        def settingsWidget(self):
            return SourceSettings()

        def pageRenderTarget(self):
            return MARKDOWN

        def pageOutputFormat(self):
            return MARKDOWN

        def artifact(self, _settings):
            captured["page_route"] = getattr(
                self,
                "_page_renderer_route_override",
                "",
            )
            return ExportArtifact(
                "Compiled manuscript",
                "book.md",
                "text/markdown",
            )

    class Converter:
        def convert(
                self, content, source_format, target_format, options):
            captured.update(
                content=content,
                source=source_format,
                target=target_format,
            )
            return ConversionArtifact(
                "[b]{}[/b]".format(content),
                "book.bbcode",
                "text/plain",
            )

    contribution = ConversionContribution(
        ExtensionDescriptor(
            "example.bbcode",
            "BBCode",
            extensions=(".bbcode",),
        ),
        Converter,
        source_formats=(MARKDOWN,),
        target_formats=(BBCODE,),
    )
    registry = PluginRegistry()
    registrar = registry.registrar("example.plugin")
    registrar.register_converter(contribution)
    registry.install("example.plugin", registrar.contributions)
    context = MagicMock()
    context.project_path = str(tmp_path)
    source = MarkdownSource(context=context)
    source_group = basicExporter(context)
    source_group.exportTo = [source]
    runtime = MagicMock()
    runtime.registry = registry
    runtime.records = {}

    groups = create_plugin_exporters(
        context,
        runtime,
        InMemoryPluginOptionStore(),
        source_exporters=[source_group],
    )

    assert len(groups) == 1
    assert len(groups[0].exportTo) == 1
    compile_format = groups[0].exportTo[0]
    assert isinstance(compile_format, PluginConversionExportFormat)
    assert compile_format.name == "BBCode"
    assert compile_format.media_type == BBCODE

    artifact = compile_format.artifact(compile_format.settingsWidget())

    assert artifact.content == "[b]Compiled manuscript[/b]"
    assert captured == {
        "content": "Compiled manuscript",
        "source": MARKDOWN,
        "target": BBCODE,
        "page_route": "text/x-bbcode|text/markdown",
    }
    assert not hasattr(source, "_page_renderer_route_override")
