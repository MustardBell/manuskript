#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import QTextEdit, qApp

from manuskript.exporter.basic import basicExporter, basicFormat
from manuskript.exporter.manuskript.BBCode import BBCode
from manuskript.exporter.manuskript.HTML import HTML
from manuskript.exporter.manuskript.markdown import markdown
from manuskript.exporter.manuskript.plainText import plainText
from manuskript.functions import appPath, safeTranslate

import os


class manuskriptExporter(basicExporter):

    name = "Manuskript"
    description = safeTranslate(qApp, "Export", "Default exporter, provides basic formats used by other exporters.")
    icon = appPath(os.path.join("icons", "Manuskript", "icon-256px.png"))

    def __init__(self, context):
        super().__init__(context)
        self.exportTo = [
            plainText(context),
            markdown(context),
            BBCode(context),
            HTML(context),
            basicFormat(
                "OPML",
                icon="text-x-opml+xml",
                context=context,
            ),
        ]

    def isValid(self):
        return True
