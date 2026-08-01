#!/usr/bin/env python
# --!-- coding: utf8 --!--
import os
import re
from PyQt5.QtGui import QFont, QTextCharFormat
from PyQt5.QtWidgets import QPlainTextEdit, qApp, QFrame, QMessageBox

from manuskript.domain.exporting import ExportArtifact
from manuskript.exporter.basic import basicFormat
from manuskript.exporter.page_routes import page_renderer_route_id
from manuskript.functions import getSaveFileNameWithSuffix, safeTranslate
from manuskript.models import outlineItem
from manuskript.ui.exporters.manuskript.plainTextSettings import exporterSettings
import logging
LOGGER = logging.getLogger(__name__)

class plainText(basicFormat):
    name = safeTranslate(qApp, "Export", "Plain text")
    description = safeTranslate(qApp, "Export", """Simplest export to plain text. Allows you to use your own markup not understood
                  by Manuskript, for example <a href='www.fountain.io'>Fountain</a>.""")
    implemented = True
    requires = {
        "Settings": True,
        "Preview": True,
    }
    icon = "text-plain"
    format_id = "plain"
    artifact_media_type = "text/plain"

    # Default settings used in self.getExportFilename. For easy subclassing when exporting plaintext.
    exportVarName = "lastPlainText"
    exportFilter = "Text files (*.txt);; Any files (*)"
    exportDefaultSuffix = ".txt"  # qt ignores the period, but it is clearer in our code to have it

    def __init__(self, context):
        super().__init__(context=context)

    def settingsWidget(self):
        w = exporterSettings(self, self.context)
        w.loadSettings()
        return w

    def previewWidget(self):
        w = QPlainTextEdit()
        w.setFrameShape(QFrame.NoFrame)
        w.setReadOnly(True)
        return w

    def output(self, settingsWidget):
        settings = settingsWidget.getSettings()
        try:
            root_item = self.context.outline_model.rootItem
            include_root = True
            content_settings = settings["Content"]
            if content_settings.get("Parent"):
                selected_root = self.context.outline_model.getItemByID(
                    content_settings.get("ParentID")
                )
                if selected_root is not None:
                    root_item = selected_root
                    include_root = False
            return self.concatenate(
                root_item,
                settings,
                include_item=include_root,
            )
        except re.error as e:
            QMessageBox.warning(
                self.context.parent,
                safeTranslate(qApp, "Export", "Error"),
                safeTranslate(
                    qApp,
                    "Export",
                    "Could not process regular expression: \n{}",
                ).format(str(e)),
            )
            return ""

    def artifact(self, settingsWidget):
        settingsWidget.writeSettings()
        project_file = getattr(self.context, "project_file", "")
        stem = os.path.splitext(os.path.basename(project_file))[0]
        return ExportArtifact(
            content=self.output(settingsWidget),
            suggested_name=(stem or "manuskript")
            + self.exportDefaultSuffix,
            media_type=self.artifact_media_type,
        )

    def getExportFilename(self, settingsWidget, varName=None, filter=None):

        if varName == None:
            varName = self.exportVarName

        if filter == None:
            filter = self.exportFilter

        settings = settingsWidget.getSettings()

        s = settings.get("Output", {})
        if varName in s:
            filename = s[varName]
        else:
            filename = ""

        filename, filter = getSaveFileNameWithSuffix(settingsWidget.parent(),
                                                     caption=safeTranslate(qApp, "Export", "Choose output file…"),
                                                     filter=filter,
                                                     directory=filename,
                                                     defaultSuffix=self.exportDefaultSuffix)

        if filename:
            s[varName] = filename
            settingsWidget.settings["Output"] = s

            # Save settings
            settingsWidget.writeSettings()

        return filename

    def export(self, settingsWidget):
        settings = settingsWidget.getSettings()

        filename = self.getExportFilename(settingsWidget)

        if filename:
            settingsWidget.writeSettings()
            content = self.output(settingsWidget)

            if not content:
                LOGGER.error("No content. Nothing saved.")
                return

            with open(filename, "wt", encoding="utf8", newline="\n") as f:
                f.write(content)

    def preview(self, settingsWidget, previewWidget):
        settings = settingsWidget.getSettings()

        # Save settings
        settingsWidget.writeSettings()

        r = self.output(settingsWidget)

        # Set preview font
        self.preparesTextEditView(previewWidget, settings["Preview"]["PreviewFont"])

        previewWidget.setPlainText(r)

    def preparesTextEditView(self, view, textFont):
        cf = QTextCharFormat()
        f = QFont()
        f.fromString(textFont)
        cf.setFont(f)
        view.setCurrentCharFormat(cf)

    def concatenate(
        self,
        item: outlineItem,
        settings,
        include_item=True,
    ) -> str:
        s = settings
        r = ""
        content_settings = s["Content"]

        # Compile status is inherited, so an excluded folder can be pruned.
        if (
            not content_settings.get("IgnoreCompile", False)
            and not item.compile()
        ):
            return ""

        # What do we include
        l = item.level()
        if (
            include_item
            and l >= 0
            and self._matchesMetadataFilters(
                item,
                content_settings,
            )
        ):

            if item.isFolder():
                if self._contentAtLevel(
                    content_settings,
                    "FolderTitle",
                    l,
                ):

                    r += self.processTitle(item.title(), l, settings)

            elif item.isText():
                if self._contentAtLevel(
                    content_settings,
                    "TextTitle",
                    l,
                ):

                    r += self.processTitle(item.title(), l, settings)

                if self._contentAtLevel(
                    content_settings,
                    "TextText",
                    l,
                ):

                    r += self.processItemText(item, settings)

        rendered_children = []
        for c in item.children():
            rendered = self.concatenate(c, settings)
            if rendered:
                rendered_children.append((c.type(), rendered))

        last_type = None
        for child_type, rendered in rendered_children:
            if last_type is not None:
                separator = {
                    ("folder", "folder"): "FF",
                    ("md", "md"): "TT",
                    ("folder", "md"): "FT",
                    ("md", "folder"): "TF",
                }[(last_type, child_type)]
                r += s["Separator"][separator]
            r += rendered
            last_type = child_type

        return r

    @staticmethod
    def _contentAtLevel(content_settings, name, level):
        value = content_settings[name]
        if not content_settings["More"]:
            return value
        return value[level] if level < len(value) else False

    def processItemText(self, item, settings):
        source = item.text()
        page_types = getattr(self.context, "page_types", None)
        if page_types is None:
            return self.processText(source, settings)
        target_format = self.pageRenderTarget()
        document = page_types.export_document(
            item,
            target_format,
            source=source,
            route_id=self.pageRendererRoute(),
        )
        if document.source_format == "markdown":
            return self.processText(document.content, settings)
        if document.source_format == target_format:
            return self.processRenderedPageText(
                document.content,
                target_format,
                settings,
            )
        raise ValueError(
            "Cannot include {} page content in a {} export."
            .format(document.source_format, target_format)
        )

    def pageRenderTarget(self):
        """Format in which this exporter composes individual pages."""
        return self.format_id or "markdown"

    def pageOutputFormat(self):
        """User-facing destination used to persist renderer routing."""
        return self.format_id or self.pageRenderTarget()

    def pageRendererRoute(self):
        override = getattr(self, "_page_renderer_route_override", None)
        if override:
            return override
        return page_renderer_route_id(
            self.pageOutputFormat(),
            self.pageRenderTarget(),
        )

    def processRenderedPageText(self, content, target_format, settings):
        """Embed an exact-format page fragment into the export source."""
        return content.rstrip("\n") + "\n"

    @staticmethod
    def _matchesMetadataFilters(item, content_settings):
        if content_settings.get("Labels"):
            selected_labels = set(
                content_settings.get("LabelValues", [])
            )
            if item.label() not in selected_labels and str(
                item.label()
            ) not in {str(value) for value in selected_labels}:
                return False
        if content_settings.get("Status"):
            selected_statuses = set(
                content_settings.get("StatusValues", [])
            )
            if item.status() not in selected_statuses and str(
                item.status()
            ) not in {str(value) for value in selected_statuses}:
                return False
        return True

    def processTitle(self, text, level, settings):
        return text + "\n"

    def processText(self, content, settings):
        s = settings["Transform"]

        if s["Dash"]:
            content = content.replace("---", "—")

        if s["Ellipse"]:
            content = content.replace("...", "…")

        if s["Spaces"]:
            o = ""
            while o != content:
                o = content
                content = content.replace("  ", " ")

        custom_replacements = list(s["Custom"])
        if s["DoubleQuotes"]:
            q = s["DoubleQuotes"].split("___")
            custom_replacements.append(
                [True, '"(.*?)"', "{}\\1{}".format(q[0], q[1]), True]
            )

        if s["SingleQuote"]:
            q = s["SingleQuote"].split("___")
            custom_replacements.append(
                [True, "'(.*?)'", "{}\\1{}".format(q[0], q[1]), True]
            )

        for enabled, A, B, reg in custom_replacements:
            if not enabled:
                continue

            if not reg:
                content = content.replace(A, B)

            else:
                content = re.sub(A, B, content)

        content += "\n"

        return content
