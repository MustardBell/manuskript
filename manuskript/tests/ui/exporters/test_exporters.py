#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Integration tests for the exporter dialog."""

from manuskript.plugins.api import (
    ConversionArtifact,
    ConversionContribution,
    ExtensionDescriptor,
)
from manuskript.media_types import BBCODE, MARKDOWN
from manuskript.ui.plugins.export_adapter import (
    PluginConversionExportFormat,
)


def test_export_dialog_loads_manager_and_restores_format(
        MWSampleProject):
    MW = MWSampleProject

    MW.doCompile()
    exporter_dialog = MW.dialog
    assert exporter_dialog.isVisible()
    available_formats = []
    for index in range(exporter_dialog.cmbExporters.count()):
        exporter_dialog.cmbExporters.setCurrentIndex(index)
        selected_exporter, selected_format = (
            exporter_dialog.getSelectedExporter()
        )
        if (
            selected_exporter
            and selected_format
            and selected_format.implemented
        ):
            available_formats.append(
                (
                    index,
                    selected_exporter.name,
                    selected_format.name,
                )
            )
    assert available_formats
    selected_index, exporter_name, format_name = available_formats[-1]
    exporter_dialog.cmbExporters.setCurrentIndex(selected_index)
    assert MW.applicationPreferences.last_exporter == exporter_name
    assert MW.applicationPreferences.last_export_format == format_name
    exporter_dialog.hide()

    exporter_dialog.openManager()
    manager = exporter_dialog.dialog
    assert manager.isVisible()
    manager.updateUi("Manuskript")
    manager.updateFormatDescription("OPML")
    assert manager.lblExportToDescription.text() == "<b>OPML:</b> "
    manager.hide()

    manager.close()
    exporter_dialog.close()

    MW.doCompile()
    restored = MW.dialog
    selected_exporter, selected_format = restored.getSelectedExporter()
    assert selected_exporter.name == exporter_name
    assert selected_format.name == format_name
    restored.close()


def test_plugin_conversion_target_uses_the_compile_dialog(
        MWSampleProject):
    class Converter:
        def convert(
                self, content, source_format, target_format, options):
            return ConversionArtifact(
                "converted:{}".format(content),
                "compiled.bbcode",
                "text/plain",
            )

    window = MWSampleProject
    registry = window.pluginRuntime.registry
    registrar = registry.registrar("test.compile-converter")
    registrar.register_converter(
        ConversionContribution(
            ExtensionDescriptor(
                "test.compile-converter.bbcode",
                "Plugin BBCode",
                extensions=(".bbcode",),
            ),
            Converter,
            source_formats=(MARKDOWN,),
            target_formats=(BBCODE,),
        )
    )
    registry.install(
        "test.compile-converter",
        registrar.contributions,
    )
    try:
        window.doCompile()
        dialog = window.dialog
        index = next(
            index
            for index in range(dialog.cmbExporters.count())
            if dialog.cmbExporters.itemText(index) == "Plugin BBCode"
        )

        dialog.cmbExporters.setCurrentIndex(index)
        _exporter, output_format = dialog.getSelectedExporter()

        assert isinstance(output_format, PluginConversionExportFormat)
        assert dialog.settingsWidget.sourceSettings is not None
        dialog.preview()
        assert dialog.previewWidget.toPlainText().startswith(
            "converted:"
        )
    finally:
        window.dialog.close()
        registry.remove_plugin("test.compile-converter")


def test_native_bbcode_is_a_usable_compile_target(MWSampleProject):
    window = MWSampleProject
    window.doCompile()
    dialog = window.dialog
    try:
        index = next(
            index
            for index in range(dialog.cmbExporters.count())
            if dialog.cmbExporters.itemText(index) == "BBCode"
        )

        dialog.cmbExporters.setCurrentIndex(index)
        exporter, output_format = dialog.getSelectedExporter()

        assert exporter.name == "Manuskript"
        assert output_format.isValid()
        assert output_format.media_type == BBCODE
        dialog.preview()
        assert dialog.previewWidget.toPlainText()
    finally:
        dialog.close()
