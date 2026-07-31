import pytest

from manuskript.plugins.api import (
    ConversionArtifact,
    ConversionContribution,
    ExportArtifact,
    ExportContribution,
    ExtensionDescriptor,
    ImportContribution,
    ImportNode,
    ImportResult,
    OptionField,
    OptionKind,
    PageExportDocument,
    PageRendererContribution,
    PageTypeContribution,
    RenderedDocument,
)
from manuskript.plugins.execution import (
    PluginConversionService,
    PluginExecutionError,
    run_export,
    run_import,
    run_page_format_renderer,
    run_page_parser,
    run_page_renderer,
)
from manuskript.plugins.registry import PluginRegistry


class ExportEngine:
    def export(self, snapshot, options):
        return ExportArtifact(
            content="{}:{}".format(
                snapshot,
                options["uppercase"],
            ),
            suggested_name="book.fb2",
            media_type="application/fb2+xml",
        )


def test_export_engine_receives_normalized_options():
    contribution = ExportContribution(
        ExtensionDescriptor("example.fb2", "FB2"),
        ExportEngine,
        options=(
            OptionField(
                "uppercase",
                "Uppercase",
                OptionKind.BOOLEAN,
                True,
            ),
        ),
    )

    artifact = run_export(contribution, "snapshot")

    assert artifact.content == "snapshot:True"
    assert artifact.suggested_name == "book.fb2"


def test_import_engine_must_return_typed_result():
    class InvalidImporter:
        def import_document(self, source, options):
            return ["not typed"]

    contribution = ImportContribution(
        ExtensionDescriptor("example.bad", "Bad"),
        InvalidImporter,
        "Bad files (*.bad)",
    )

    with pytest.raises(PluginExecutionError, match="ImportResult"):
        run_import(contribution, "book.bad")


def test_import_engine_returns_portable_nodes():
    class Importer:
        def import_document(self, source, options):
            return ImportResult((
                ImportNode(
                    title="Imported",
                    text="from " + source,
                ),
            ))

    contribution = ImportContribution(
        ExtensionDescriptor("example.data", "Data"),
        Importer,
        "Data files (*.data)",
    )

    result = run_import(contribution, "book.data")

    assert result.nodes[0].title == "Imported"
    assert result.nodes[0].text == "from book.data"


def test_conversion_service_routes_declared_formats():
    class Converter:
        def convert(
                self, content, source_format, target_format, options):
            return ConversionArtifact(
                "{}:{}>{}".format(
                    content,
                    source_format,
                    target_format,
                )
            )

    contribution = ConversionContribution(
        ExtensionDescriptor("example.convert", "Converter"),
        Converter,
        source_formats=("markdown",),
        target_formats=("bbcode",),
    )
    registry = PluginRegistry()
    registrar = registry.registrar("example.plugin")
    registrar.register_converter(contribution)
    registry.install("example.plugin", registrar.contributions)

    result = PluginConversionService(registry).convert(
        "Text",
        "markdown",
        "bbcode",
    )

    assert result.content == "Text:markdown>bbcode"


def test_conversion_service_rejects_untyped_results():
    class InvalidConverter:
        def convert(
                self, content, source_format, target_format, options):
            return "not typed"

    contribution = ConversionContribution(
        ExtensionDescriptor("example.bad-convert", "Bad converter"),
        InvalidConverter,
        source_formats=("one",),
        target_formats=("two",),
    )
    registry = PluginRegistry()
    registrar = registry.registrar("example.plugin")
    registrar.register_converter(contribution)
    registry.install("example.plugin", registrar.contributions)

    with pytest.raises(
        PluginExecutionError,
        match="ConversionArtifact",
    ):
        PluginConversionService(registry).convert(
            "Text",
            "one",
            "two",
        )


def test_reading_renderer_returns_typed_inert_projection():
    class Renderer:
        def render(self, source):
            return RenderedDocument("<b>{}</b>".format(source))

    contribution = PageTypeContribution(
        ExtensionDescriptor("example.reader", "Reader"),
        "Example page",
        renderer_factory=Renderer,
    )

    rendered = run_page_renderer(contribution, "Text")

    assert rendered.html == "<b>Text</b>"


def test_reading_renderer_receives_the_page_parser_model():
    class Parser:
        def parse(self, source):
            return {"semantic_text": source.upper()}

    class Renderer:
        def render(self, model):
            return RenderedDocument(model["semantic_text"])

    contribution = PageTypeContribution(
        ExtensionDescriptor("example.semantic", "Semantic page"),
        "Semantic page",
        parser_factory=Parser,
        renderer_factory=Renderer,
    )

    rendered = run_page_renderer(contribution, "Text")

    assert rendered.html == "TEXT"


def test_reading_renderer_rejects_untyped_results():
    class InvalidRenderer:
        def render(self, source):
            return source

    contribution = PageTypeContribution(
        ExtensionDescriptor("example.bad-reader", "Bad reader"),
        "Bad page",
        renderer_factory=InvalidRenderer,
    )

    with pytest.raises(PluginExecutionError, match="RenderedDocument"):
        run_page_renderer(contribution, "Text")


def test_page_parser_and_renderer_return_a_typed_source_format():
    class Parser:
        def parse(self, source):
            return {"source": source}

    class Renderer:
        def render(self, model, target_format, options):
            return PageExportDocument(
                "{}:{}".format(target_format, model["source"]),
                target_format,
            )

    page_type = PageTypeContribution(
        ExtensionDescriptor("example.page", "Page"),
        "Example page",
        parser_factory=Parser,
    )
    renderer = PageRendererContribution(
        ExtensionDescriptor("example.page.bbcode", "Page BBCode"),
        page_type_id="example.page",
        renderer_factory=Renderer,
        target_formats=("bbcode",),
    )

    model = run_page_parser(page_type, "Text")
    rendered = run_page_format_renderer(
        renderer,
        model,
        "bbcode",
    )

    assert rendered == PageExportDocument("bbcode:Text", "bbcode")
