#!/usr/bin/env python
# --!-- coding: utf8 --!--
from manuskript.converters.abstractConverter import abstractConverter

import logging
LOGGER = logging.getLogger(__name__)

try:
    import markdown as MD
except ImportError:
    MD = None


class markdownConverter(abstractConverter):
    """
    Converter using python module markdown.
    """

    name = "python module markdown"

    @classmethod
    def isValid(cls):
        return MD != None

    @classmethod
    def convert(cls, markdown):
        if not cls.isValid():
            LOGGER.error("markdownConverter is called but not valid.")
            return ""

        html = MD.markdown(markdown)
        return html
