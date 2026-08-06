"""Two real editors on one document, typing into one text.

The buffer's own behaviour is covered in
tests/services/test_document_buffers.py. These are the tests that need
actual textEditViews bound to an actual project, because what is being
claimed is about widgets: a keystroke in one editor is visible in the other
at once, and neither can overwrite the other.
"""

from PyQt5.QtCore import Qt

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.views.textEditView import textEditView


def document(window, title="Scene"):
    """A fresh outline item, and the index of its text."""
    root = window.mdlOutline.rootItem
    item = outlineItem(title=title, parent=root)
    index = window.mdlOutline.getIndexByID(item.ID())
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


def editor_on(window, index):
    """A text editor bound to a document, as a pane or a window would be."""
    view = textEditView(
        window,
        settings=window.settingsManager,
    )
    view.set_text_editor_context(window.textEditorContext)
    view.setCurrentModelIndex(index)
    return view


def test_a_keystroke_in_one_editor_is_in_the_other_at_once(MWEmptyProject):
    """What two windows on one document are for. No timer, no round trip
    through the model: there is one text, and both are looking at it.
    """
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    second = editor_on(window, index)
    try:
        assert first.document() is second.document()

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
        window.mdlOutline.setData(index, "Something else entirely.")

        assert editor.toPlainText() == "What I am still typ"
    finally:
        discard(editor)


def test_one_document_one_highlighter(MWEmptyProject):
    """Two highlighters on one QTextDocument overwrite each other's
    per-block state, which is where multi-line markup is tracked. So the
    buffer hands out its one highlighter and refuses to make a second.
    """
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    first.setHighlighting(True)
    first.setCurrentModelIndex(index)
    second = editor_on(window, index)
    try:
        buffer = first._buffer
        assert buffer is second._buffer
        highlighter = buffer.highlighter
        assert highlighter is not None

        # Both views resolve to that one, rather than each keeping its own
        # reference to whatever it built.
        assert first.highlighter is highlighter
        assert second.highlighter is highlighter
    finally:
        discard(first, second)


def test_the_highlighter_follows_the_editor_being_worked_in(MWEmptyProject):
    """Focus mode reads a cursor, and a shared document has only one set of
    character formats, so the dimming can only follow one view. The one with
    focus is the right one.
    """
    window = MWEmptyProject
    _item, index = document(window)
    first = editor_on(window, index)
    first.setHighlighting(True)
    first.setCurrentModelIndex(index)
    second = editor_on(window, index)
    try:
        buffer = first._buffer
        assert buffer.highlighter is not None

        buffer.focused(second)
        assert buffer.highlighter.editor is second

        buffer.focused(first)
        assert buffer.highlighter.editor is first
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
    window.mdlCharacter.addCharacter(name="Someone")
    index = window.mdlCharacter.index(0, 0)
    assert not hasattr(window.mdlCharacter, "getIndexByID")

    editor = textEditView(window, settings=window.settingsManager)
    editor.set_text_editor_context(window.textEditorContext)
    try:
        editor.setCurrentModelIndex(index)

        assert editor._buffer is None
        # And it still works, on text of its own.
        editor.setPlainText("A private note.")
        assert editor.toPlainText() == "A private note."
    finally:
        discard(editor)
