#!/usr/bin/env python
# --!-- coding: utf8 --!--

from manuskript.importer.folderImporter import folderImporter
from manuskript.importer.markdownImporter import markdownImporter
from manuskript.importer.opmlImporter import opmlImporter
from manuskript.importer.mindMapImporter import mindMapImporter
from manuskript.importer.pandocImporters import markdownPandocImporter, \
    odtPandocImporter, ePubPandocImporter, docXPandocImporter, HTMLPandocImporter, \
    rstPandocImporter, LaTeXPandocImporter, OPMLPandocImporter

importers = [
    # Internal
    markdownImporter,
    folderImporter,
    opmlImporter,
    mindMapImporter,

    # Pandoc
    markdownPandocImporter,
    odtPandocImporter,
    ePubPandocImporter,
    docXPandocImporter,
    HTMLPandocImporter,
    rstPandocImporter,
    LaTeXPandocImporter,
    OPMLPandocImporter,
    ]


def create_importers(
        plugin_runtime=None,
        plugin_option_store=None,
):
    values = [importer_type() for importer_type in importers]
    if plugin_runtime is not None:
        from manuskript.ui.plugins.import_adapter import (
            create_plugin_importers,
        )
        values.extend(
            create_plugin_importers(
                plugin_runtime,
                plugin_option_store,
            )
        )
    return values
