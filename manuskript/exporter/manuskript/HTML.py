#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QPlainTextEdit, qApp, QTabWidget, QFrame, QTextEdit

from manuskript.exporter.manuskript.markdown import markdown, markdownSettings
from manuskript.ui.views.webView import webView
from manuskript.ui.exporters.manuskript.plainTextSettings import exporterSettings
from manuskript.functions import safeTranslate
from manuskript.media_types import HTML as HTML_MEDIA_TYPE

import logging
import os

try:
    import markdown as MD
except ImportError:
    MD = None

LOGGER = logging.getLogger(__name__)

class HTML(markdown):
    name = "HTML"
    description = safeTranslate(qApp, "Export", "Basic HTML output using the Python module 'markdown'.")
    InvalidBecause = safeTranslate(qApp, "Export", "Python module 'markdown'.")
    icon = "text-html"
    media_type = HTML_MEDIA_TYPE

    exportVarName = "lastManuskriptHTML"
    exportFilter = "HTML files (*.html);; Any files (*)"
    exportDefaultSuffix = ".html"

    def isValid(self):
        return MD != None

    def settingsWidget(self):
        w = markdownSettings(self, self.context)
        w.loadSettings()
        return w

    def previewWidget(self):
        t = QTabWidget()
        t.setDocumentMode(True)
        t.setStyleSheet("""
            QTabBar::tab{
                background-color: #BBB;
                padding: 3px 25px;
                border: none;
            }

            QTabBar::tab:selected, QTabBar::tab:hover{
                background-color:skyblue;
            }
        """)
        w0 = QPlainTextEdit()
        w0.setFrameShape(QFrame.NoFrame)
        w0.setReadOnly(True)
        w1 = QPlainTextEdit()
        w1.setFrameShape(QFrame.NoFrame)
        w1.setReadOnly(True)
        t.addTab(w0, safeTranslate(qApp, "Export", "Markdown source"))
        t.addTab(w1, safeTranslate(qApp, "Export", "HTML Source"))
        
        if webView:
            w2 = webView()
            t.addTab(w2, safeTranslate(qApp, "Export", "HTML Output"))

        t.setCurrentIndex(2)
        return t

    def htmlAugmentations(self):
        """What plugins add to Markdown for this rendering, if anything.

        Asked of the context per rendering rather than held: a plugin can be
        enabled or disabled while an export dialog is open, and the answer
        must be current when the button is pressed.
        """
        provider = getattr(self.context, "html_augmentations", None)
        if provider is None:
            return []
        try:
            return list(provider())
        except Exception:
            LOGGER.exception(
                "Cannot read what plugins add to Markdown; exporting "
                "without their additions."
            )
            return []

    def output(self, settingsWidget):
        html = MD.markdown(
            markdown.output(self, settingsWidget),
            extensions=self.htmlAugmentations(),
        )
        return html

    def preview(self, settingsWidget, previewWidget):
        settings = settingsWidget.getSettings()

        # Save settings
        settingsWidget.writeSettings()

        md = markdown.output(self, settingsWidget)
        html = MD.markdown(md, extensions=self.htmlAugmentations())
        path = os.path.join(self.projectPath(), "dummy.html")

        self.preparesTextEditView(previewWidget.widget(0), settings["Preview"]["PreviewFont"])
        self.preparesTextEditViewMarkdown(previewWidget.widget(0), settings)
        previewWidget.widget(0).setPlainText(md)
        self.preparesTextEditView(previewWidget.widget(1), settings["Preview"]["PreviewFont"])
        previewWidget.widget(1).setPlainText(html)
        w2 = previewWidget.widget(2)
        if isinstance(w2, QTextEdit):
            w2.setHtml(html)
        else:
            w2.setHtml(html, QUrl.fromLocalFile(path))
