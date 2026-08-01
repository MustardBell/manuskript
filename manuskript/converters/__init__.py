#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""
The converters package provide functions to quickly convert on the fly from
one format to another. It is responsible to check what external library are
present, and do the job as best as possible with what we have in hand.
"""

from manuskript.converters.abstractConverter import abstractConverter
from manuskript.converters.pandocConverter import pandocConverter
#from manuskript.converters.markdownConverter import markdownConverter
from PyQt5.QtWidgets import QTextEdit


def HTML2MD(html, on_error=None):

    # Convert using pandoc
    if pandocConverter.isValid():
        return pandocConverter.convert(
            html,
            _from="html",
            to="markdown",
            on_error=on_error,
        )

    # Convert to plain text using QTextEdit
    return HTML2PlainText(html)


def HTML2PlainText(html, on_error=None):
    """
    Convert from HTML to plain text.
    """

    if pandocConverter.isValid():
        return pandocConverter.convert(
            html,
            _from="html",
            to="plain",
            on_error=on_error,
        )

    # Last resort: probably resource inefficient
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    e = QTextEdit()
    e.setHtml(html)
    return e.toPlainText()
