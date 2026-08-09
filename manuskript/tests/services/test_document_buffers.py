"""Two views of one document share one text.

The editor has always been able to show a document twice -- split panes do
it, and a second workspace window does it -- and each view used to hold its
own QTextDocument. Two buffers for one document meant text could be lost:
whichever reached the model last won, and a view reloaded itself from the
model whenever anything changed it, mid-sentence included.

These tests are about the buffer that replaced them. The Qt-free ones are
here; the ones that need real editors are in
tests/ui/views/test_shared_text_buffers.py.
"""

from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.services.document_buffers import (
    DocumentBufferRegistry,
    TextBuffer,
)


def model_with(text):
    model = QStandardItemModel()
    model.appendRow(QStandardItem(text))
    return model, model.index(0, 0)


def test_two_asks_for_one_document_get_one_buffer():
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")

    first = registry.buffer_for(model, index, 0, "7", view="a")
    second = registry.buffer_for(model, index, 0, "7", view="b")

    assert first is second
    assert first.views == ("a", "b")
    assert len(registry) == 1


def test_the_buffer_starts_from_what_the_model_holds():
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")

    buffer = registry.buffer_for(model, index, 0, "7")

    assert buffer.text() == "Chapter one."


def test_a_document_with_no_identity_keeps_its_own_text():
    """A character's notes, a multiple selection, a read-only html view --
    nothing the outline can name, so nothing to share it with.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Loose text.")

    assert registry.buffer_for(model, index, 0, None) is None
    assert registry.buffer_for(model, index, 0, "") is None
    assert len(registry) == 0


def test_two_documents_do_not_share_a_buffer():
    registry = DocumentBufferRegistry()
    model = QStandardItemModel()
    model.appendRow(QStandardItem("One."))
    model.appendRow(QStandardItem("Two."))

    first = registry.buffer_for(model, model.index(0, 0), 0, "1")
    second = registry.buffer_for(model, model.index(1, 0), 0, "2")

    assert first is not second
    assert len(registry) == 2


def test_the_model_is_told_only_after_the_pause():
    """The 500ms delay is a feel, not an implementation detail, so it
    survives the move from the view to the buffer.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7")

    buffer.document.setPlainText("Chapter one, revised.")

    assert buffer.dirty is True
    assert model.data(index) == "Chapter one."

    buffer.flush()

    assert buffer.dirty is False
    assert model.data(index) == "Chapter one, revised."


def test_a_model_change_from_elsewhere_does_not_eat_what_is_being_typed():
    """The reported defect. An undo in another window, a rename, a
    revision restore -- all reach the model while somebody is mid-sentence
    somewhere else, and the sentence is the newer of the two.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7")

    buffer.document.setPlainText("Chapter one, and I am still typ")
    assert buffer.dirty is True

    # Something else writes to the model and asks the buffer to reload.
    model.setData(index, "Chapter one.")
    assert buffer.load("Chapter one.") is False

    assert buffer.text() == "Chapter one, and I am still typ"

    # And the newer text is what the model ends up with.
    buffer.flush()
    assert model.data(index) == "Chapter one, and I am still typ"


def test_a_quiet_buffer_does_take_a_change_from_elsewhere():
    """Declining while dirty is not refusing to listen. A view showing a
    document somebody renamed elsewhere has to show the new text.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7")

    assert buffer.dirty is False
    assert buffer.load("Chapter one, renamed elsewhere.") is True
    assert buffer.text() == "Chapter one, renamed elsewhere."


def test_loading_does_not_make_the_buffer_look_edited():
    """Taking text in is not typing it. A load that started the submit
    timer would write the model's own text back to it.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7")

    buffer.load("Chapter one, from elsewhere.")

    assert buffer.dirty is False


def test_the_last_view_leaving_writes_out_what_it_had():
    """A view going away is not a reason to lose what was typed into it,
    and once it is gone there is nobody left to submit later.
    """
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7", view="a")
    buffer.document.setPlainText("Typed and then closed.")

    registry.detach("a", buffer)

    assert model.data(index) == "Typed and then closed."
    assert len(registry) == 0


def test_a_buffer_outlives_a_view_while_another_still_shows_it():
    """One window closing is not the document closing."""
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7", view="a")
    registry.buffer_for(model, index, 0, "7", view="b")

    registry.detach("a", buffer)

    assert len(registry) == 1
    assert registry.buffer_for(model, index, 0, "7") is buffer
    assert buffer.views == ("b",)


def test_flushing_writes_every_pending_buffer():
    """What a save, an autosave and a project close all need first."""
    registry = DocumentBufferRegistry()
    model = QStandardItemModel()
    model.appendRow(QStandardItem("One."))
    model.appendRow(QStandardItem("Two."))
    first = registry.buffer_for(model, model.index(0, 0), 0, "1")
    second = registry.buffer_for(model, model.index(1, 0), 0, "2")
    first.document.setPlainText("One, edited.")
    second.document.setPlainText("Two, edited.")

    assert registry.flush() == 2

    assert model.data(model.index(0, 0)) == "One, edited."
    assert model.data(model.index(1, 0)) == "Two, edited."
    assert registry.flush() == 0


def test_a_buffer_keeps_non_breaking_spaces():
    """toPlainText replaces them; the manuscript is entitled to keep them."""
    registry = DocumentBufferRegistry()
    model, index = model_with("start")
    buffer = registry.buffer_for(model, index, 0, "7")

    buffer.document.setPlainText("one two")
    buffer.flush()

    assert model.data(index) == "one two"


def test_closing_the_project_writes_out_and_forgets():
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7", view="a")
    buffer.document.setPlainText("Edited just before closing.")

    registry.forget_all()

    assert model.data(index) == "Edited just before closing."
    assert len(registry) == 0


def test_a_buffer_for_a_vanished_row_says_nothing_rather_than_raising():
    registry = DocumentBufferRegistry()
    model, index = model_with("Chapter one.")
    buffer = registry.buffer_for(model, index, 0, "7")
    buffer.document.setPlainText("Edited.")

    model.removeRow(0)

    assert buffer.submit() is False


def test_a_buffer_needs_no_registry_to_be_useful():
    """It is a plain object about one document, which is what makes it
    testable without a project at all.
    """
    model, index = model_with("Chapter one.")

    buffer = TextBuffer(model, index, 0)
    buffer.load("Chapter one.")

    assert buffer.text() == "Chapter one."
    assert buffer.dirty is False
