from unittest.mock import MagicMock

import pytest
from PyQt5.QtGui import QTextCursor

from manuskript.settingsManager import SettingsManager
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
    MarkdownPresentationState,
)
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
