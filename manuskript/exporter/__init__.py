#!/usr/bin/env python
# --!-- coding: utf8 --!--

from manuskript.exporter.manuskript import manuskriptExporter
from manuskript.exporter.pandoc import pandocExporter


def create_exporters(context):
    """Build a fresh exporter graph for one project and dialog."""
    return [
        manuskriptExporter(context),
        pandocExporter(context),
    ]


def get_exporter_by_name(exporters, name):
    for e in exporters:
        if e.name == name:
            return e

    return None
