#!/usr/bin/env python
# --!-- coding: utf8 --!--

from manuskript.exporter.manuskript import manuskriptExporter
from manuskript.exporter.pandoc import pandocExporter


def create_exporters(
        context,
        plugin_runtime=None,
        plugin_option_store=None):
    """Build a fresh exporter graph for one project and dialog."""
    exporters = [
        manuskriptExporter(context),
        pandocExporter(context),
    ]
    if plugin_runtime is not None:
        from manuskript.ui.plugins.export_adapter import (
            create_plugin_exporters,
        )
        exporters.extend(
            create_plugin_exporters(
                context,
                plugin_runtime,
                plugin_option_store,
                source_exporters=exporters,
            )
        )
    return exporters


def get_exporter_by_name(exporters, name):
    for e in exporters:
        if e.name == name:
            return e

    return None
