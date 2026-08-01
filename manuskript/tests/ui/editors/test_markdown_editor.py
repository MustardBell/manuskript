from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import qApp

from manuskript.settingsManager import SettingsManager
from manuskript.ui.editors.MDFunctions import MDFormatSelection
from manuskript.ui.highlighters import (
    MarkdownHighlighter,
    MarkdownState,
    MarkdownTokenType,
)
from manuskript.ui.views.MDEditView import MDEditView


def make_editor():
    return MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )


def test_unbound_markdown_editor_installs_markdown_highlighter():
    editor = make_editor()

    assert isinstance(editor.highlighter, MarkdownHighlighter)


def test_setext_heading_is_highlighted_and_reported():
    editor = make_editor()
    headings = []
    editor.highlighter.headingFound.connect(
        lambda level, text, block: headings.append(
            (level, text, block.blockNumber())
        )
    )

    editor.setPlainText("Heading\n=======\nBody")
    editor.highlighter.rehighlight()
    qApp.processEvents()

    first = editor.document().findBlockByNumber(0)
    second = editor.document().findBlockByNumber(1)
    assert first.userState() == (
        MarkdownState.MarkdownStateSetextHeading1Line1
    )
    assert second.userState() == (
        MarkdownState.MarkdownStateSetextHeading1Line2
    )
    assert (1, "Heading", 0) in headings


def test_markdown_mentions_have_an_explicit_theme():
    editor = make_editor()

    mention_theme = editor.highlighter.theme[
        MarkdownTokenType.TokenMention
    ]

    assert mention_theme["bold"]
    assert mention_theme["color"].isValid()


def test_indent_and_unindent_all_selected_blocks():
    editor = make_editor()
    editor.setPlainText("one\ntwo")
    cursor = editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.setTextCursor(cursor)

    editor.indentText()
    assert editor.toPlainText() == "    one\n    two"

    editor.unindentText()
    assert editor.toPlainText() == "one\ntwo"


def test_tab_and_backtab_route_to_markdown_indentation():
    editor = make_editor()
    editor.setPlainText("line")
    editor.moveCursor(QTextCursor.End)
    tab = MagicMock()
    tab.key.return_value = Qt.Key_Tab
    tab.modifiers.return_value = Qt.NoModifier

    editor.keyPressEvent(tab)
    assert editor.toPlainText() == "    line"

    tab.key.return_value = Qt.Key_Backtab
    editor.keyPressEvent(tab)
    assert editor.toPlainText() == "line"


def test_clear_format_removes_inline_and_block_markdown():
    editor = make_editor()
    source = (
        "# Heading\n"
        "Setext\n"
        "======\n"
        "> 1. **Bold** and [link](https://example.com)\n"
        "```\n"
        "    code\n"
        "```\n"
        "<!-- note -->"
    )

    assert editor.clearedFormat(source) == (
        "Heading\n"
        "Setext\n"
        "\n"
        "Bold and link\n"
        "\n"
        "code\n"
        "\n"
        "note"
    )
    assert "note" not in editor.clearedFormatForStats(source)


@pytest.mark.parametrize(
    ("style", "markup"),
    ((0, "**"), (1, "*"), (2, "`")),
)
def test_legacy_markdown_format_function_routes_to_editor(
    style,
    markup,
):
    editor = MagicMock()

    MDFormatSelection(editor, style)

    editor.insertFormattingMarkup.assert_called_once_with(markup)


def test_legacy_markdown_format_function_rejects_unknown_style():
    with pytest.raises(ValueError, match="Unknown Markdown"):
        MDFormatSelection(MagicMock(), 99)
