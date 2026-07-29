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


def test_interaction_rectangle_updates_are_coalesced():
    editor = make_editor()
    qApp.processEvents()
    updates = []
    editor.interactionRectUpdateTimer.timeout.connect(
        lambda: updates.append(True)
    )

    for _ in range(20):
        editor.document().documentLayoutChanged.emit()
    qApp.processEvents()

    assert updates == [True]


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


def select_text(editor, text):
    source = editor.toPlainText()
    python_start = source.index(text)
    start = len(
        source[:python_start].encode("utf-16-le")
    ) // 2
    length = len(text.encode("utf-16-le")) // 2
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(
        start + length,
        QTextCursor.KeepAnchor,
    )
    editor.setTextCursor(cursor)


def test_bold_is_a_toggle_instead_of_stacking_delimiters():
    editor = make_editor()
    source = "was it the blown precision and"
    editor.setPlainText(source)
    select_text(editor, "precision")

    editor.bold()

    assert editor.toPlainText() == (
        "was it the blown **precision** and"
    )
    assert editor.textCursor().selectedText() == "precision"

    editor.bold()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "precision"


def test_bold_removes_markers_included_in_selection():
    editor = make_editor()
    editor.setPlainText("some **bold words** here")
    select_text(editor, "**bold words**")

    editor.bold()

    assert editor.toPlainText() == "some bold words here"
    assert editor.textCursor().selectedText() == "bold words"


def test_bold_splits_an_enclosing_strong_span():
    editor = make_editor()
    source = (
        "**Taras finished his tea, set the mug on the "
        "floor, and said:**"
    )
    editor.setPlainText(source)
    select_text(editor, "tea")

    editor.bold()

    assert editor.toPlainText() == (
        "**Taras finished his** tea, "
        "**set the mug on the floor, and said:**"
    )
    assert editor.textCursor().selectedText() == "tea"

    editor.bold()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "tea"


def test_bold_splits_underscore_strong_without_changing_prose():
    editor = make_editor()
    source = "__Keep this word, and the rest strong.__"
    editor.setPlainText(source)
    select_text(editor, "word")

    editor.bold()

    assert editor.toPlainText() == (
        "__Keep this__ word, __and the rest strong.__"
    )
    assert editor.textCursor().selectedText() == "word"

    editor.bold()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "word"


def test_bold_leaves_selected_outer_whitespace_outside_markers():
    editor = make_editor()
    editor.setPlainText("before selected after")
    select_text(editor, " selected ")

    editor.bold()

    assert editor.toPlainText() == "before **selected** after"
    assert editor.textCursor().selectedText() == "selected"


def test_bold_toggle_handles_utf16_positions():
    editor = make_editor()
    editor.setPlainText("🙂 before **selected** after")
    select_text(editor, "selected")

    editor.bold()

    assert editor.toPlainText() == "🙂 before selected after"
    assert editor.textCursor().selectedText() == "selected"


def test_italic_splits_and_rejoins_an_enclosing_span():
    editor = make_editor()
    source = "*Keep this word, and the rest italic.*"
    editor.setPlainText(source)
    select_text(editor, "word")

    editor.italic()

    assert editor.toPlainText() == (
        "*Keep this* word, *and the rest italic.*"
    )
    assert editor.textCursor().selectedText() == "word"

    editor.italic()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "word"


def test_italic_recognizes_underscore_delimiters():
    editor = make_editor()
    editor.setPlainText("_some italic words_")
    select_text(editor, "italic")

    editor.italic()

    assert editor.toPlainText() == (
        "_some_ italic _words_"
    )
    assert editor.textCursor().selectedText() == "italic"


def test_underline_uses_inline_html_and_toggles_it_off():
    editor = make_editor()
    source = "some underlined words"
    editor.setPlainText(source)
    select_text(editor, "underlined")

    editor.underline()

    assert editor.toPlainText() == (
        "some <u>underlined</u> words"
    )
    assert editor.textCursor().selectedText() == "underlined"
    assert editor.highlighter.theme[
        MarkdownTokenType.TokenUnderline
    ]["underline"]

    editor.underline()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "underlined"


def test_underline_splits_and_rejoins_an_enclosing_html_span():
    editor = make_editor()
    source = "<u>Keep this word, and the rest underlined.</u>"
    editor.setPlainText(source)
    select_text(editor, "word")

    editor.underline()

    assert editor.toPlainText() == (
        "<u>Keep this</u> word, "
        "<u>and the rest underlined.</u>"
    )
    assert editor.textCursor().selectedText() == "word"

    editor.underline()

    assert editor.toPlainText() == source
    assert editor.textCursor().selectedText() == "word"


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
