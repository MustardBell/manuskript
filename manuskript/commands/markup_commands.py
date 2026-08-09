"""Commands that apply markup through the active editor.

The command names describe author intent rather than Markdown delimiters.
An editor remains responsible for interpreting that intent through its active
markup profile, so a plugin can replace Markdown without replacing menus or
reaching into ``MainWindow``.
"""

from enum import Enum


class MarkupCommand(str, Enum):
    HEADING_SETEXT_1 = "heading-setext-1"
    HEADING_SETEXT_2 = "heading-setext-2"
    HEADING_ATX_1 = "heading-atx-1"
    HEADING_ATX_2 = "heading-atx-2"
    HEADING_ATX_3 = "heading-atx-3"
    HEADING_ATX_4 = "heading-atx-4"
    HEADING_ATX_5 = "heading-atx-5"
    HEADING_ATX_6 = "heading-atx-6"
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    STRIKE = "strike"
    VERBATIM = "verbatim"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"
    COMMENT_LINES = "comment-lines"
    UNORDERED_LIST = "unordered-list"
    ORDERED_LIST = "ordered-list"
    BLOCKQUOTE = "blockquote"
    COMMENT_BLOCK = "comment-block"
    CLEAR_FORMAT = "clear-format"


_HANDLERS = {
    MarkupCommand.HEADING_SETEXT_1: ("titleSetext", (1,)),
    MarkupCommand.HEADING_SETEXT_2: ("titleSetext", (2,)),
    MarkupCommand.HEADING_ATX_1: ("titleATX", (1,)),
    MarkupCommand.HEADING_ATX_2: ("titleATX", (2,)),
    MarkupCommand.HEADING_ATX_3: ("titleATX", (3,)),
    MarkupCommand.HEADING_ATX_4: ("titleATX", (4,)),
    MarkupCommand.HEADING_ATX_5: ("titleATX", (5,)),
    MarkupCommand.HEADING_ATX_6: ("titleATX", (6,)),
    MarkupCommand.BOLD: ("bold", ()),
    MarkupCommand.ITALIC: ("italic", ()),
    MarkupCommand.UNDERLINE: ("underline", ()),
    MarkupCommand.STRIKE: ("strike", ()),
    MarkupCommand.VERBATIM: ("verbatim", ()),
    MarkupCommand.SUPERSCRIPT: ("superscript", ()),
    MarkupCommand.SUBSCRIPT: ("subscript", ()),
    MarkupCommand.COMMENT_LINES: ("commentLine", ()),
    MarkupCommand.UNORDERED_LIST: ("unorderedList", ()),
    MarkupCommand.ORDERED_LIST: ("orderedList", ()),
    MarkupCommand.BLOCKQUOTE: ("blockquote", ()),
    MarkupCommand.COMMENT_BLOCK: ("comment", ()),
    MarkupCommand.CLEAR_FORMAT: ("clearFormat", ()),
}


class MarkupCommandRouter:
    """Dispatch authoring intent to the active markup-capable editor."""

    def __init__(self, target_provider):
        self._target_provider = target_provider

    def can_dispatch(self, command):
        target, handler, _arguments = self._resolve(command)
        return target is not None and callable(handler)

    def dispatch(self, command, *_signal_args):
        target, handler, arguments = self._resolve(command)
        if target is None or not callable(handler):
            return False
        handler(*arguments)
        return True

    def _resolve(self, command):
        command = MarkupCommand(command)
        method_name, arguments = _HANDLERS[command]
        target = self._target_provider()
        visited = set()

        while target is not None and id(target) not in visited:
            visited.add(id(target))
            resolver = getattr(target, "markup_command_target", None)
            if not callable(resolver):
                break
            resolved = resolver(command)
            if resolved is target:
                break
            target = resolved

        return target, getattr(target, method_name, None), arguments
