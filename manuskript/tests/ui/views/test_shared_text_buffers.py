"""Two real editors on one document, typing into one text authority.

The buffer's own behaviour is covered in
tests/services/test_document_buffers.py. These are the tests that need
actual textEditViews bound to an actual project, because what is being
claimed is about widgets: a keystroke in one editor is visible in the other
at once, neither can overwrite the other, and presentation stays local.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextBlockFormat
from PyQt5.QtWidgets import QTextEdit, qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.views.textEditView import textEditView


def document(window, title="Scene"):
    """A fresh outline item, and the index of its text."""
    root = window.projectRuntime.models.outline.rootItem
    item = outlineItem(title=title, _type="md", parent=root)
    index = window.projectRuntime.models.outline.getIndexByID(item.ID())
    return item, index.sibling(index.row(), Outline.text)


def discard(*views):
    """Take test editors off the window again.

    The test window is a session-wide singleton, so an editor merely
    deleteLater()'d -- with no event loop to run the deletion -- stays
    among its children and is then found by every later test that walks
    them, still bound to a project that has since closed.
    """
    for view in views:
        view._releaseSharedBuffer()
        view.setParent(None)


def editor_on(window, index, editor_class=textEditView):
    """A text editor bound to a document, as a pane or a window would be."""
    view = editor_class(
        window,
        settings=window.projectRuntime.settingsManager,
    )
    view.set_text_editor_context(
        window.workspaceProject.text_editor_context
    )
    view.setCurrentModelIndex(index)
    return view


def test_a_keystroke_in_one_editor_is_in_the_other_at_once(MWEmptyProject):
    """What two windows on one document are for. No timer, no round trip
    through the model: there is one text authority, and both project it.
    """
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        assert first._buffer is second._buffer
        assert first.document() is not second.document()

        first.setPlainText("Chapter one.")

        assert second.toPlainText() == "Chapter one."

        # And the other way, because neither is the owner.
        second.append("Chapter two.")
        assert "Chapter two." in first.toPlainText()
    finally:
        discard(first, second)


def test_each_editor_keeps_its_own_cursor(MWEmptyProject):
    """One text, two places to be in it. Sharing the buffer must not mean
    sharing where the person is reading.
    """
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        first.setPlainText("One two three four five.")

        cursor = first.textCursor()
        cursor.setPosition(0)
        first.setTextCursor(cursor)
        cursor = second.textCursor()
        cursor.movePosition(cursor.End)
        second.setTextCursor(cursor)

        assert first.textCursor().position() == 0
        assert second.textCursor().position() == len(
            "One two three four five."
        )
    finally:
        discard(first, second)


def test_a_change_from_elsewhere_does_not_eat_what_is_being_typed(
        MWEmptyProject):
    """The reported defect, at the level it was reported: an edit lands in
    the model from somewhere that is not this editor -- an undo in the other
    window, a rename, a revision restore -- while this one has unsubmitted
    text. The unsubmitted text is newer and stays.
    """
    window = MWEmptyProject
    _item, index = document(window)
    editor = editor_on(window, index)
    try:
        editor.setPlainText("What I am still typ")
        assert editor._buffer.dirty is True

        # Something other than this editor writes to the model, which is
        # what used to replace the editor's contents mid-word.
        window.projectRuntime.models.outline.setData(index, "Something else entirely.")

        assert editor.toPlainText() == "What I am still typ"
    finally:
        discard(editor)


def test_each_projection_has_its_own_highlighter(MWEmptyProject):
    """Highlighting is presentation, not shared document state."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    first.setHighlighting(True)
    first.setCurrentModelIndex(index)
    second = editor_on(window, index)
    try:
        buffer = first._buffer
        assert buffer is second._buffer
        second.setHighlighting(True)
        second.setCurrentModelIndex(index)

        assert first.highlighter is not None
        assert second.highlighter is not None
        assert first.highlighter is not second.highlighter
        assert first.highlighter.document() is first.document()
        assert second.highlighter.document() is second.document()
    finally:
        discard(first, second)


def test_projection_formatting_is_not_a_shared_text_edit(MWEmptyProject):
    """Line layout and highlighting must not dirty or enter master history."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        first.setPlainText("The same text remains the same text.")
        first._buffer.flush()
        first._buffer.settle()

        cursor = first.textCursor()
        block_format = QTextBlockFormat(cursor.blockFormat())
        block_format.setTopMargin(27)
        cursor.setBlockFormat(block_format)

        assert first._buffer.text() == "The same text remains the same text."
        assert second.toPlainText() == "The same text remains the same text."
        assert first._buffer.dirty is False
        assert first._buffer.document.isUndoAvailable() is False
        assert second.textCursor().blockFormat().topMargin() != 27
    finally:
        discard(first, second)


def test_each_highlighter_stays_with_its_own_editor(MWEmptyProject):
    """Focusing one projection must not retarget another one's renderer."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    first.setHighlighting(True)
    first.setCurrentModelIndex(index)
    second = editor_on(window, index)
    try:
        second.setHighlighting(True)
        second.setCurrentModelIndex(index)

        second.setFocus(Qt.OtherFocusReason)
        qApp.processEvents()
        assert first.highlighter.editor is first
        assert second.highlighter.editor is second

        first.setFocus(Qt.OtherFocusReason)
        qApp.processEvents()
        assert first.highlighter.editor is first
        assert second.highlighter.editor is second
    finally:
        discard(first, second)


def test_two_widths_wrap_independently_while_text_stays_shared(
        MWEmptyProject):
    """The defect behind the split: text is shared; layout width is not."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        prose = "A paragraph of ordinary prose that needs to wrap. " * 30
        first.setPlainText(prose)
        for editor, width in ((first, 260), (second, 620)):
            # Exercise two real top-level panes. As otherwise-unmanaged
            # children of the session's MainWindow, Qt clamps both test
            # widgets to the same leftover child geometry.
            editor.setParent(None)
            editor.setLineWrapMode(QTextEdit.WidgetWidth)
            editor.resize(width, 400)
            editor.show()
        qApp.processEvents()

        assert first.document() is not second.document()
        assert first.toPlainText() == second.toPlainText() == prose
        assert first.document().textWidth() != second.document().textWidth()
        assert first.document().documentLayout().documentSize().height() > (
            second.document().documentLayout().documentSize().height()
        )

        second.append("Written in the wide pane.")
        assert "Written in the wide pane." in first.toPlainText()
    finally:
        discard(first, second)


def test_two_markdown_modes_can_edit_the_same_text_at_once(MWEmptyProject):
    """Presentation mode belongs to a pane even when text is shared."""
    window = MWEmptyProject
    _item, index = document(window)
    source = editor_on(window, index, MDEditView)
    live = editor_on(window, index, MDEditView)
    try:
        source.setPresentationMode(MarkdownPresentationMode.SOURCE)
        live.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)

        assert source.presentationMode is MarkdownPresentationMode.SOURCE
        assert live.presentationMode is MarkdownPresentationMode.LIVE_PREVIEW
        assert source.document() is not live.document()

        source.insertPlainText("**Shared text, separate presentations.**")
        assert live.toPlainText() == source.toPlainText()
        assert live.presentationMode is MarkdownPresentationMode.LIVE_PREVIEW
    finally:
        discard(source, live)


def test_undo_from_either_projection_reaches_both(MWEmptyProject):
    """History belongs to the shared text authority, not either layout."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        first.insertPlainText("One change")
        assert first.toPlainText() == second.toPlainText() == "One change"

        second.undo()
        assert first.toPlainText() == second.toPlainText() == ""

        first.redo()
        assert first.toPlainText() == second.toPlainText() == "One change"
    finally:
        discard(first, second)


def test_projection_sync_preserves_manuscript_characters(MWEmptyProject):
    """Mirroring deltas must not normalize prose on its way to another pane."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        text = "First paragraph.\n\nNBSP:\u00a0kept; astral: 🐁."
        first.setPlainText(text)

        assert first.toPlainText() == text
        assert second.toPlainText() == text
        assert first._buffer.text() == text

        first._buffer.flush()
        assert index.data() == text
    finally:
        discard(first, second)


def test_shared_context_menu_undo_uses_authoritative_history(
        MWEmptyProject):
    """The standard menu must not target a projection's disabled stack."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        first.insertPlainText("Undo me")
        menu = second.createStandardContextMenu()
        undo_action = menu.actions()[0]

        assert undo_action.isEnabled()
        undo_action.trigger()
        assert first.toPlainText() == second.toPlainText() == ""
    finally:
        discard(first, second)


def test_an_editor_leaving_does_not_take_the_text_from_the_other(
        MWEmptyProject):
    """Closing one window is not closing the document."""
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        first.setPlainText("Still being read next door.")
        buffer = second._buffer

        # The first editor goes to look at something else entirely.
        _other, elsewhere = document(window, title="Another scene")
        first.setCurrentModelIndex(elsewhere)

        assert buffer.views == (second,)
        assert second.toPlainText() == "Still being read next door."
    finally:
        discard(first, second)


def test_a_model_that_cannot_name_a_document_shares_nothing(
        MWEmptyProject):
    """Only the outline names its documents in a way two views can agree
    on. A character's notes and a world item live in models with no such
    notion, so those keep the private buffer they always had.
    """
    window = MWEmptyProject
    window.projectRuntime.models.characters.addCharacter(name="Someone")
    index = window.projectRuntime.models.characters.index(0, 0)
    assert not hasattr(window.projectRuntime.models.characters, "getIndexByID")

    editor = textEditView(
        window,
        settings=window.projectRuntime.settingsManager,
    )
    editor.set_text_editor_context(
        window.workspaceProject.text_editor_context
    )
    try:
        editor.setCurrentModelIndex(index)

        assert editor._buffer is None
        # And it still works, on text of its own.
        editor.setPlainText("A private note.")
        assert editor.toPlainText() == "A private note."
    finally:
        discard(editor)
