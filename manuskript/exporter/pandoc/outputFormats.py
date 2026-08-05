#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import qApp

from manuskript.exporter.pandoc.abstractOutput import abstractOutput
from manuskript.functions import safeTranslate
from manuskript.media_types import DOCX, EPUB, HTML, ODT


class ePub(abstractOutput):
    name = "ePub"
    description = safeTranslate(qApp, "Export", """Books that don't kill trees.""")
    icon = "application-epub+zip"

    exportVarName = "lastPandocePub"
    toFormat = "epub"
    media_type = EPUB
    representation_media_type = HTML
    exportFilter = "ePub files (*.epub);; Any files (*)"
    exportDefaultSuffix = ".epub"


class OpenDocument(abstractOutput):
    name = "OpenDocument"
    description = safeTranslate(qApp, "Export", "OpenDocument format. Used by LibreOffice for example.")

    exportVarName = "lastPandocODT"
    toFormat = "odt"
    media_type = ODT
    icon = "application-vnd.oasis.opendocument.text"
    exportFilter = "OpenDocument files (*.odt);; Any files (*)"
    exportDefaultSuffix = ".odt"


class DocX(abstractOutput):
    name = "DocX"
    description = safeTranslate(qApp, "Export", "Microsoft Office (.docx) document.")

    exportVarName = "lastPandocDocX"
    toFormat = "docx"
    media_type = DOCX
    icon = "application-vnd.openxmlformats-officedocument.wordprocessingml.document"
    exportFilter = "DocX files (*.docx);; Any files (*)"
    exportDefaultSuffix = ".docx"

