#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import QGroupBox, qApp, QVBoxLayout, QCheckBox

import logging

from manuskript.exporter.manuskript.plainText import plainText
from manuskript.functions import safeTranslate
from manuskript.media_types import MARKDOWN
from manuskript.plugins.api import ConversionRequest
from manuskript.ui.highlighters import MMDHighlighter
from manuskript.ui.exporters.manuskript.plainTextSettings import exporterSettings


LOGGER = logging.getLogger(__name__)


class markdown(plainText):
    name = "Markdown"
    description = safeTranslate(qApp, "Export", """Just like plain text, excepts adds markdown titles.
                          Presupposes that texts are formatted in markdown.""")

    exportVarName = "lastManuskriptMarkdown"
    exportFilter = "Markdown files (*.md);; Any files (*)"
    exportDefaultSuffix = ".md"
    icon = "text-x-markdown"
    media_type = MARKDOWN

    def settingsWidget(self):
        w = markdownSettings(self, self.context)
        w.loadSettings()
        return w

    def augmentations(self):
        """What plugins add to this exporter's own conversion, if anything.

        Every exporter below this one starts from Manuskript's Markdown and
        produces its own ``media_type``, so that pair is the route, and the
        exporter is the code entitled to name it. Naming a format in the
        plugin contract instead would make one privileged and leave every
        other reachable only through something more generic.

        Here rather than in each exporter because each was otherwise asking
        the same question in its own words, and one of them had not thought
        to ask at all -- so an addition contributed for its route was applied
        by one exporter and silently ignored by the next.

        Asked of the context per rendering rather than held: a plugin can be
        enabled or disabled while an export dialog is open, and the answer
        must be current when the button is pressed.
        """
        provider = getattr(self.context, "conversion_augmentations", None)
        if provider is None:
            return []
        try:
            return list(provider(ConversionRequest(
                source_format=MARKDOWN,
                target_format=self.media_type,
            )))
        except Exception:
            LOGGER.exception(
                "Cannot read what plugins add to this conversion; "
                "exporting without their additions."
            )
            return []

    def preparesTextEditViewMarkdown(self, view, settings):
        if settings["Preview"]["MarkdownHighlighter"]:
            self.highlighter = MMDHighlighter(view)
        else:
            self.highlighter = None

    def preview(self, settingsWidget, previewWidget):
        settings = settingsWidget.getSettings()

        # Save settings
        settingsWidget.writeSettings()

        # Prepares text edit
        self.preparesTextEditViewMarkdown(previewWidget, settingsWidget.settings)
        self.preparesTextEditView(previewWidget, settings["Preview"]["PreviewFont"])

        previewWidget.setPlainText(self.output(settingsWidget))

    def processTitle(self, text, level, settings):
        return "{} {}\n".format(
            "#" * (level + 1),
            text
        )


class markdownSettings(exporterSettings):
    def __init__(self, _format, context, parent=None):
        exporterSettings.__init__(self, _format, context, parent)

        # Adds markdown syntax highlighter setting
        w = self.toolBox.widget(self.toolBox.count() - 1)
        self.grpMarkdown = QGroupBox(self.tr("Markdown"))
        self.grpMarkdown.setLayout(QVBoxLayout())
        self.chkMarkdownHighlighter = QCheckBox(safeTranslate(qApp, "Export", "Preview with highlighter."))
        self.grpMarkdown.layout().addWidget(self.chkMarkdownHighlighter)

        w.layout().insertWidget(w.layout().count() - 1, self.grpMarkdown)

    def updateFromSettings(self):
        exporterSettings.updateFromSettings(self)

        s = self.settings["Preview"]
        val = s.get("MarkdownHighlighter", False)
        self.chkMarkdownHighlighter.setChecked(val)

    def getSettings(self):
        self.settings = exporterSettings.getSettings(self)
        self.settings["Preview"]["MarkdownHighlighter"] = self.chkMarkdownHighlighter.isChecked()

        return self.settings
