from unittest.mock import MagicMock

import pytest
from PyQt5.QtGui import QFont, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import qApp

from manuskript.settingsManager import SettingsManager
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    MarkdownPresentationState,
)
from manuskript.ui.highlighters import MarkdownHighlighter
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.views.text_editor_context import TextEditorContext


def make_context(settings, presentation):
    return TextEditorContext(
        settings=settings,
        reload_fonts=MagicMock(),
        create_character=MagicMock(),
        create_plot=MagicMock(),
        create_world_item=MagicMock(),
        invoke_outline_command=MagicMock(),
        markdown_presentation=presentation,
    )


def format_at(editor, position):
    block = editor.document().findBlock(position)
    position_in_block = position - block.position()
    for format_range in block.layout().formats():
        if (
            format_range.start
            <= position_in_block
            < format_range.start + format_range.length
        ):
            return format_range.format
    return QTextCharFormat()


def test_markdown_presentation_mode_defines_display_policy():
    assert MarkdownPresentationMode.SOURCE.is_editable
    assert not MarkdownPresentationMode.SOURCE.renders_markdown
    assert not MarkdownPresentationMode.SOURCE.reveals_active_block

    assert MarkdownPresentationMode.LIVE_PREVIEW.is_editable
    assert MarkdownPresentationMode.LIVE_PREVIEW.renders_markdown
    assert MarkdownPresentationMode.LIVE_PREVIEW.reveals_active_block

    assert not MarkdownPresentationMode.READING.is_editable
    assert MarkdownPresentationMode.READING.renders_markdown
    assert not MarkdownPresentationMode.READING.reveals_active_block


def test_markdown_presentation_mode_normalizes_persisted_values():
    assert MarkdownPresentationMode.from_value(
        "LIVE_PREVIEW"
    ) is MarkdownPresentationMode.LIVE_PREVIEW

    with pytest.raises(
        ValueError,
        match="Unknown Markdown presentation mode",
    ):
        MarkdownPresentationMode.from_value("wysiwyg")


def test_presentation_state_persists_and_emits_real_transitions():
    settings = SettingsManager()
    state = MarkdownPresentationState(settings)
    transitions = []
    state.modeChanged.connect(transitions.append)

    state.set_mode(MarkdownPresentationMode.SOURCE)
    state.set_mode("source")
    state.set_mode("reading")

    assert transitions == [
        MarkdownPresentationMode.SOURCE,
        MarkdownPresentationMode.READING,
    ]
    assert settings.textEditor["markdownMode"] == "reading"


def test_presentation_state_repairs_an_unknown_persisted_value():
    settings = SettingsManager()
    settings.textEditor["markdownMode"] = "wysiwyg"

    state = MarkdownPresentationState(settings)

    assert state.mode is MarkdownPresentationMode.LIVE_PREVIEW
    assert settings.textEditor["markdownMode"] == "live-preview"


def test_editor_mode_switch_preserves_source_selection_and_undo_state():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("before **selected** after")
    cursor = editor.textCursor()
    start = editor.toPlainText().index("selected")
    cursor.setPosition(start)
    cursor.setPosition(
        start + len("selected"),
        QTextCursor.KeepAnchor,
    )
    editor.setTextCursor(cursor)

    editor.setPresentationMode(MarkdownPresentationMode.READING)

    assert editor.isReadOnly()
    assert editor.toPlainText() == "before **selected** after"
    assert editor.textCursor().selectedText() == "selected"
    assert not editor.document().isUndoAvailable()

    editor.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)

    assert not editor.isReadOnly()
    assert editor.textCursor().selectedText() == "selected"


def test_shared_presentation_state_synchronizes_attached_editors():
    settings = SettingsManager()
    state = MarkdownPresentationState(settings)
    context = make_context(settings, state)
    first = MDEditView(spellcheck=False, settings=settings)
    second = MDEditView(spellcheck=False, settings=settings)
    first.set_text_editor_context(context)
    second.set_text_editor_context(context)

    state.set_mode("reading")

    assert first.presentationMode is MarkdownPresentationMode.READING
    assert second.presentationMode is MarkdownPresentationMode.READING
    assert first.isReadOnly()
    assert second.isReadOnly()


def test_html_display_editor_remains_read_only_in_editable_modes():
    editor = MDEditView(
        html="<h1>Folder</h1>",
        spellcheck=False,
        settings=SettingsManager(),
    )

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)

    assert editor.isReadOnly()


def test_source_mode_shows_markup_without_rendering_emphasis():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**bold** and *italic*")

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)
    editor.highlighter.rehighlight()
    qApp.processEvents()

    opening_bold = format_at(editor, 0)
    bold_text = format_at(editor, 2)
    italic_text = format_at(
        editor,
        editor.toPlainText().index("italic"),
    )
    assert not opening_bold.property(
        MarkdownHighlighter.MarkupHiddenProperty
    )
    assert bold_text.fontWeight() != QFont.Bold
    assert not italic_text.fontItalic()


def test_live_preview_reveals_only_the_active_blocks_markup():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**first**\n**second**")
    second_block = editor.document().findBlockByNumber(1)
    cursor = editor.textCursor()
    cursor.setPosition(second_block.position() + 2)
    editor.setTextCursor(cursor)

    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    editor.highlighter.rehighlight()
    qApp.processEvents()

    first_marker = format_at(editor, 0)
    first_text = format_at(editor, 2)
    second_marker = format_at(editor, second_block.position())
    assert first_marker.property(
        MarkdownHighlighter.MarkupHiddenProperty
    )
    assert first_marker.foreground().color().alpha() == 0
    assert first_marker.fontPointSize() != pytest.approx(0.01)
    assert first_text.fontWeight() == QFont.Bold
    assert not second_marker.property(
        MarkdownHighlighter.MarkupHiddenProperty
    )


def test_live_preview_rehighlights_old_and_new_active_blocks():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**first**\n**second**")
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    second_block = editor.document().findBlockByNumber(1)
    cursor = editor.textCursor()
    cursor.setPosition(second_block.position() + 2)
    editor.setTextCursor(cursor)
    qApp.processEvents()

    cursor.setPosition(2)
    editor.setTextCursor(cursor)
    qApp.processEvents()

    first_marker = format_at(editor, 0)
    second_marker = format_at(editor, second_block.position())
    assert not first_marker.property(
        MarkdownHighlighter.MarkupHiddenProperty
    )
    assert second_marker.property(
        MarkdownHighlighter.MarkupHiddenProperty
    )


def test_live_preview_keeps_list_markers_layout_stable_when_visible():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("- First item\n- Second item")
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    editor.resize(480, 360)
    editor.show()
    try:
        qApp.processEvents()
        second_block = editor.document().findBlockByNumber(1)
        marker = format_at(editor, second_block.position())
        assert not marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
    finally:
        editor.hide()


def test_live_preview_hides_markup_without_changing_font_metrics():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText(
        "# Heading\n\nA <u>stable underline</u>."
    )
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    editor.resize(480, 360)
    editor.show()
    try:
        qApp.processEvents()
        tag_position = editor.toPlainText().index("<u>")
        marker_format = format_at(editor, tag_position)
        assert marker_format.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert marker_format.foreground().color().alpha() == 0
        assert marker_format.fontPointSize() != pytest.approx(0.01)
    finally:
        editor.hide()


def test_reading_mode_is_a_rendered_projection_of_untouched_source():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    source_document = editor.document()
    source = (
        "# Heading\n\n"
        "Some **bold**, *italic*, and <u>underlined</u> text.\n\n"
        "- first\n"
        "- second"
    )
    editor.setPlainText(source)

    editor.setPresentationMode(MarkdownPresentationMode.READING)
    qApp.processEvents()

    assert editor.document() is source_document
    assert editor.toPlainText() == source
    assert not editor.readingView.isHidden()
    assert editor.readingView.isReadOnly()
    assert editor.readingView.toPlainText() == (
        "Heading\n"
        "Some bold, italic, and underlined text.\n"
        "first\n"
        "second"
    )
    rendered_html = editor.readingView.toHtml()
    assert "<ul" in rendered_html
    assert "font-weight:600" in rendered_html
    assert "text-decoration: underline" in rendered_html


def test_reading_projection_refreshes_when_source_changes():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**first**")
    editor.setPresentationMode(MarkdownPresentationMode.READING)

    editor.document().setPlainText("*second*")
    qApp.processEvents()

    assert editor.toPlainText() == "*second*"
    assert editor.readingView.toPlainText() == "second"
    assert "font-style:italic" in editor.readingView.toHtml()


def test_leaving_reading_mode_restores_the_same_editable_document():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    source_document = editor.document()
    editor.setPlainText("editable")
    editor.setPresentationMode(MarkdownPresentationMode.READING)

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)

    assert editor.document() is source_document
    assert editor.toPlainText() == "editable"
    assert editor.readingView.isHidden()
    assert not editor.isReadOnly()
