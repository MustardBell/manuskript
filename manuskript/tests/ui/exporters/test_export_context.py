import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript import exporter
from manuskript.exporter.context import (
    ExportContext,
    ExportContextProvider,
)
from manuskript.exporter.page_routes import page_renderer_routes
from manuskript.exporter.pandoc import pandocExporter
from manuskript.exporter.pandoc.abstractPlainText import pandocSettings
from manuskript.plugins.api import (
    ConversionArtifact,
    ConversionContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.plugin_options import InMemoryPluginOptionStore
from manuskript.media_types import BBCODE, MARKDOWN

busy_cursor_module = importlib.import_module(
    "manuskript.ui.busy_cursor"
)


def make_context(
    project_file="/tmp/novel.msk",
    process_runner=None,
):
    tool_paths = MagicMock()
    tool_paths.get.return_value = ""
    process_runner = process_runner or MagicMock()
    return ExportContext(
        project_file=project_file,
        outline_model=MagicMock(),
        flat_data_model=QStandardItemModel(1, 8),
        label_model=MagicMock(),
        status_model=MagicMock(),
        parent=MagicMock(),
        tool_paths=tool_paths,
        process_runner=process_runner,
    )


def test_export_context_resolves_project_directory():
    context = make_context("/work/novel/manuscript.msk")

    assert context.project_path == "/work/novel"


def test_export_context_provider_resolves_live_project_sources():
    first_models = SimpleNamespace(
        outline=object(),
        flat_data=object(),
        labels=object(),
        statuses=object(),
    )
    second_models = SimpleNamespace(
        outline=object(),
        flat_data=object(),
        labels=object(),
        statuses=object(),
    )
    state = {
        "project": "/work/first.msk",
        "models": first_models,
        "page_types": object(),
    }
    provider = ExportContextProvider(
        project_file=lambda: state["project"],
        models=lambda: state["models"],
        parent=object(),
        page_types=lambda: state["page_types"],
    )

    first = provider.create()
    state["project"] = "/work/second.msk"
    state["models"] = second_models
    state["page_types"] = object()
    second = provider.create()

    assert first.project_file == "/work/first.msk"
    assert first.outline_model is first_models.outline
    assert second.project_file == "/work/second.msk"
    assert second.outline_model is second_models.outline
    assert second.page_types is state["page_types"]


def test_exporter_factory_builds_isolated_project_graphs():
    context = make_context()

    first = exporter.create_exporters(context)
    second = exporter.create_exporters(context)

    assert first[0] is not second[0]
    assert first[1] is not second[1]
    for first_exporter, second_exporter in zip(first, second):
        assert first_exporter.exportTo is not second_exporter.exportTo
        for first_format, second_format in zip(
            first_exporter.exportTo,
            second_exporter.exportTo,
        ):
            assert first_format is not second_format
            assert first_format.context is context
            assert second_format.context is context


def test_exporter_factory_always_exposes_native_bbcode():
    exporters = exporter.create_exporters(make_context())

    bbcode = exporters[0].getFormatByName("BBCode")

    assert bbcode is not None
    assert bbcode.isValid()
    assert bbcode.media_type == BBCODE


def test_page_renderer_routes_come_from_usable_export_formats():
    exporters = exporter.create_exporters(make_context())

    routes = page_renderer_routes(exporters[:1])

    assert {route.id for route in routes} == {
        "text/plain|text/plain",
        "text/markdown|text/markdown",
        "text/x-bbcode|text/x-bbcode",
        "text/html|text/html",
    }
    assert "OPML" not in {route.label for route in routes}


def test_exporter_factory_exposes_plugin_converters_as_compile_formats():
    class Converter:
        def convert(
                self, content, source_format, target_format, options):
            return ConversionArtifact(content)

    registry = PluginRegistry()
    registrar = registry.registrar("example.converter")
    registrar.register_converter(
        ConversionContribution(
            ExtensionDescriptor("example.bbcode", "Plugin BBCode"),
            Converter,
            source_formats=(MARKDOWN,),
            target_formats=(BBCODE,),
        )
    )
    registry.install("example.converter", registrar.contributions)
    runtime = SimpleNamespace(registry=registry, records={})

    exporters = exporter.create_exporters(
        make_context(),
        plugin_runtime=runtime,
        plugin_option_store=InMemoryPluginOptionStore(),
    )

    plugin_format = exporters[-1].getFormatByName("Plugin BBCode")
    assert plugin_format is not None
    assert plugin_format.source_format.name == "Markdown"
    assert plugin_format.source_media_type == MARKDOWN
    assert plugin_format.media_type == BBCODE
    plugin_route = next(
        route
        for route in page_renderer_routes(exporters)
        if route.id == "text/x-bbcode|text/markdown"
    )
    assert plugin_route.label == "Plugin BBCode"
    assert plugin_route.exporter_name == "example.converter"


def test_plain_text_output_uses_context_outline_root():
    context = make_context()
    context.outline_model.rootItem = object()
    plain_text = exporter.create_exporters(context)[0].getFormatByName(
        "Plain text"
    )
    settings_widget = MagicMock()
    settings = {"Content": {}}
    settings_widget.getSettings.return_value = settings

    with patch.object(
        plain_text,
        "concatenate",
        return_value="Rendered manuscript",
    ) as concatenate:
        output = plain_text.output(settings_widget)

    assert output == "Rendered manuscript"
    concatenate.assert_called_once_with(
        context.outline_model.rootItem,
        settings,
        include_item=True,
    )


def test_pandoc_metadata_comes_from_context_flat_data():
    context = make_context()
    context.flat_data_model.setItem(0, 0, QStandardItem("My Novel"))
    context.flat_data_model.setItem(0, 1, QStandardItem("A Subtitle"))
    context.flat_data_model.setItem(0, 6, QStandardItem("A. Writer"))
    pandoc = pandocExporter(context)

    assert pandoc.metadata_arguments() == [
        "--variable=title:My Novel",
        "--variable=subtitle:A Subtitle",
        "--variable=author:A. Writer",
        "--metadata=title:My Novel",
    ]


def test_pandoc_metadata_supplies_nonempty_default_title():
    pandoc = pandocExporter(make_context())

    assert pandoc.metadata_arguments() == ["--metadata=title:Untitled"]


def test_pandoc_exposes_bbcode_when_selected_binary_supports_it():
    pandoc = pandocExporter(make_context())
    pandoc.run = MagicMock(
        return_value="html\nmarkdown\nbbcode\n"
    )

    with patch.object(pandoc, "isValid", return_value=True):
        bbcode = pandoc.getFormatByName("BBCode")

        assert bbcode.toFormat == "bbcode"
        assert bbcode.exportDefaultSuffix == ".bbcode"
        assert bbcode.isValid()
        assert pandoc.output_formats() == frozenset(
            {"html", "markdown", "bbcode"}
        )
    pandoc.run.assert_called_once_with(
        ["--list-output-formats"]
    )


def test_pandoc_hides_bbcode_when_selected_binary_lacks_writer():
    pandoc = pandocExporter(make_context())
    pandoc.run = MagicMock(return_value="html\nmarkdown\n")

    with patch.object(pandoc, "isValid", return_value=True):
        bbcode = pandoc.getFormatByName("BBCode")

        assert not bbcode.isValid()
    assert "3.8.3" in bbcode.InvalidBecause
    pandoc.run.assert_called_once_with(
        ["--list-output-formats"]
    )


def test_pandoc_refreshes_output_formats_after_path_change():
    context = make_context()
    pandoc = pandocExporter(context)
    pandoc.run = MagicMock(
        side_effect=[
            "html\n",
            "html\nbbcode\n",
        ]
    )

    with patch.object(pandoc, "isValid", return_value=True):
        assert not pandoc.supports_output_format("bbcode")

        pandoc.setCustomPath("/opt/pandoc/bin/pandoc")

        assert pandoc.supports_output_format("bbcode")
    assert pandoc.run.call_count == 2
    context.tool_paths.set.assert_called_once_with(
        "pandoc",
        "/opt/pandoc/bin/pandoc",
    )


def test_pandoc_restores_cursor_when_process_start_fails():
    runner = MagicMock()
    runner.run.side_effect = OSError("pandoc failed")
    pandoc = pandocExporter(
        make_context(process_runner=runner)
    )

    with patch.object(
        pandoc, "isValid", return_value=2
    ), patch.object(
        busy_cursor_module, "qApp"
    ) as application:
        with pytest.raises(OSError, match="pandoc failed"):
            pandoc.convert("content", [])

    application.setOverrideCursor.assert_called_once()
    application.restoreOverrideCursor.assert_called_once_with()


def test_pandoc_latex_defaults_match_supported_template_values():
    settings = pandocSettings.settingsList

    assert settings["latex-ps"].vals == ["letter", "a4", "a5"]
    assert settings["latex-fs"].type == "combo"
    assert settings["latex-fs"].vals == ["10pt", "11pt", "12pt"]
    assert {
        "scrartcl",
        "scrreprt",
        "scrbook",
    }.issubset(settings["latex-class"].vals)
    assert settings["latex-indent"].arg == "--variable=indent"
    assert settings["latex-block-headings"].minVersion == [2, 0]
