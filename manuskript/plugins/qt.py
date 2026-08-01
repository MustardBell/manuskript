"""Optional Qt-side base classes for markup plugin implementations."""

from manuskript.ui.highlighters import BasicHighlighter


class PluginHighlighter(BasicHighlighter):
    """Base for a replacement markup syntax highlighter."""


class MarkupHighlighterExtension:
    """Base for highlighting layered onto a compatible base markup."""

    def __init__(self, editor=None):
        self.editor = editor

    def highlight_block(self, highlighter, text):
        raise NotImplementedError


class MarkupBehavior:
    """Optional editor behavior for a markup contribution."""

    def __init__(self, editor=None):
        self.editor = editor

    def key_press_event(self, editor, event):
        return False

    def command(self, editor, command, *arguments):
        return False

    def plain_text(self, editor, text, remove_comments=False):
        return None
