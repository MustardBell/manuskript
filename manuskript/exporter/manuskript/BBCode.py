from PyQt5.QtWidgets import qApp

from manuskript.converters.markdownToBBCode import markdown_to_bbcode
from manuskript.exporter.manuskript.markdown import markdown
from manuskript.exporter.manuskript.plainText import plainText
from manuskript.functions import safeTranslate
from manuskript.ui.exporters.manuskript.plainTextSettings import (
    exporterSettings,
)


class BBCode(markdown):
    name = "BBCode"
    description = safeTranslate(
        qApp,
        "Export",
        "Native forum BBCode output. Does not require Pandoc.",
    )
    icon = "text-plain"
    format_id = "bbcode"
    artifact_media_type = "text/plain"

    exportVarName = "lastManuskriptBBCode"
    exportFilter = "BBCode files (*.bbcode *.txt);; Any files (*)"
    exportDefaultSuffix = ".bbcode"

    def settingsWidget(self):
        widget = exporterSettings(self, self.context)
        widget.loadSettings()
        return widget

    def preview(self, settingsWidget, previewWidget):
        plainText.preview(self, settingsWidget, previewWidget)

    def processTitle(self, text, level, settings):
        heading = min(6, max(1, level + 1))
        return "[h{0}]{1}[/h{0}]\n".format(heading, text)

    def processText(self, text, settings):
        transformed = plainText.processText(self, text, settings)
        return markdown_to_bbcode(transformed)
