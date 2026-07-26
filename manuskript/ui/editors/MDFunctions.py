#!/usr/bin/env python
# -*- coding: utf-8 -*-

MARKUP_BY_STYLE = {
    0: "**",
    1: "*",
    2: "`",
}

def MDFormatSelection(editor, style):
    """
    Formats the current selection of ``editor`` in the format given by ``style``, 
    style being:
        0: bold
        1: italic
        2: code
    """
    try:
        markup = MARKUP_BY_STYLE[style]
    except KeyError as error:
        raise ValueError(
            "Unknown Markdown selection style: {}".format(style)
        ) from error
    editor.insertFormattingMarkup(markup)
