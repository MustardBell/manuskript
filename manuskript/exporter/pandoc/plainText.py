#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import qApp

from manuskript.exporter.pandoc.abstractPlainText import abstractPlainText
from manuskript.functions import safeTranslate
from manuskript.media_types import (
    BBCODE,
    LATEX,
    MARKDOWN,
    OPML,
    RST,
)


class markdown(abstractPlainText):
    name = "Markdown"
    description = safeTranslate(qApp, "Export", """Export to markdown, using pandoc. Allows more formatting options
    than the basic manuskript exporter.""")
    icon = "text-x-markdown"

    exportVarName = "lastPandocMarkdown"
    toFormat = "markdown"
    media_type = MARKDOWN
    exportFilter = "Markdown files (*.md);; Any files (*)"
    exportDefaultSuffix = ".md"


class reST(abstractPlainText):
    name = "reST"
    description = safeTranslate(qApp, "Export", """reStructuredText is a lightweight markup language.""")

    exportVarName = "lastPandocreST"
    toFormat = "rst"
    media_type = RST
    representation_media_type = RST
    icon = "text-plain"
    exportFilter = "reST files (*.rst);; Any files (*)"
    exportDefaultSuffix = ".rst"


class latex(abstractPlainText):
    name = "LaTeX"
    description = safeTranslate(qApp, "Export", """LaTeX is a word processor and document markup language used to create
                                              beautiful documents.""")

    exportVarName = "lastPandocLatex"
    toFormat = "latex"
    media_type = LATEX
    representation_media_type = LATEX
    icon = "text-x-tex"
    exportFilter = "Tex files (*.tex);; Any files (*)"
    exportDefaultSuffix = ".tex"


class OPML(abstractPlainText):
    name = "OPML"
    description = safeTranslate(qApp, "Export", """The purpose of this format is to provide a way to exchange information
                                              between outliners and Internet services that can be browsed or controlled
                                              through an outliner.""")

    exportVarName = "lastPandocOPML"
    toFormat = "opml"
    media_type = OPML
    icon = "text-x-opml+xml"
    exportFilter = "OPML files (*.opml);; Any files (*)"
    exportDefaultSuffix = ".opml"


class BBCode(abstractPlainText):
    name = "BBCode"
    description = safeTranslate(
        qApp,
        "Export",
        "Bulletin Board Code used by many forums and community platforms.",
    )
    InvalidBecause = safeTranslate(
        qApp,
        "Export",
        "Pandoc with BBCode output support (3.8.3 or newer).",
    )

    exportVarName = "lastPandocBBCode"
    toFormat = "bbcode"
    media_type = BBCODE
    representation_media_type = BBCODE
    icon = "text-plain"
    exportFilter = "BBCode files (*.bbcode *.txt);; Any files (*)"
    exportDefaultSuffix = ".bbcode"

    def isValid(self):
        return self.exporter.supports_output_format(self.toFormat)
