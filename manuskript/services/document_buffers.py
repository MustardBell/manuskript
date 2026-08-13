"""One text authority per document, projected into every view showing it.

A document open in two windows -- or in two panes of one window, which the
editor has always allowed -- used to mean two QTextDocuments. Each ran its
own 500ms timer to submit into the model, and each reloaded itself whenever
the model changed. Two buffers standing for one document is the same
duplication the project runtime removed everywhere else, and here it cost
text: a change reaching the model from anywhere replaced whatever was being
typed somewhere else, mid-word, with no way back.

So the buffer belongs to the project, beside the models and the undo stack.
It keeps one undisplayed QTextDocument as the text and undo authority. Each
view receives its own projection document: keystrokes are mirrored through
the authority immediately, while wrap width, layout, highlighting, cursor,
scroll position, selection, and presentation mode remain local to the view.
"""

import logging

from PyQt5.QtCore import QObject, QPersistentModelIndex, QTimer
from PyQt5.QtGui import QTextCursor, QTextDocument

from manuskript.domain.text import (
    PLAIN_TRANSLATION_TABLE,
    as_text,
    plain_text,
)


LOGGER = logging.getLogger(__name__)

#: How long after the last keystroke the buffer writes into the model. The
#: same delay the individual views used, kept because it is a feel, not an
#: implementation detail.
SUBMIT_DELAY = 500


class TextBuffer(QObject):
    """One document's live text, and everything that is true of it once.

    The timer, dirty flag, and undo history live here because there may be
    several views. Highlighting and layout do not: they are projections of
    text at a particular width and in a particular presentation mode.
    """

    def __init__(self, model, index, column, parent=None):
        super().__init__(parent)
        self.model = model
        # Persistent, so a row moving or going away is noticed rather
        # than written to by stale coordinates.
        self.index = (
            index
            if isinstance(index, QPersistentModelIndex)
            else QPersistentModelIndex(index)
        )
        self.column = column
        # Monotonic source revision shared by every projection.  Layout and
        # highlighting never advance it; only changes to the canonical text
        # do.  Portable analyzers use it to reject results for older prose.
        self.revision = 0
        self.document = QTextDocument(self)
        # QTextDocument only emits its granular contentsChange signal once
        # it has a layout. The master is never painted, but its deltas are
        # what let projections synchronize without replacing whole texts.
        self.document.documentLayout()
        self._views = []
        self._projections = {}
        self._origin_view = None
        self._applying_projection = False
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setInterval(SUBMIT_DELAY)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.submit)
        self.document.contentsChanged.connect(self._touched)
        self.document.contentsChange.connect(self._master_changed)

    # ------------------------------------------------------------ views

    @property
    def views(self):
        return tuple(self._views)

    def attach(self, view):
        if view not in self._views:
            self._views.append(view)
        projection = self._projections.get(view)
        if projection is None:
            projection = QTextDocument(self)
            projection.documentLayout()
            # Undo belongs to the master. A view invokes it through the
            # buffer; keeping a second stack here would make the same edit
            # independently undoable in every pane.
            projection.setUndoRedoEnabled(False)
            self._replace_projection_text(projection, self.text())
            projection.contentsChange.connect(
                lambda position, removed, added, owner=view:
                self._projection_changed(owner, position, removed, added)
            )
            self._projections[view] = projection
        return projection

    def document_for(self, view):
        return self._projections.get(view)

    def detach(self, view):
        """Let a view go. The text stays as long as anybody is reading it.

        Its pending edits are written out first: a view going away is not a
        reason to lose what was typed into it, and with the last view gone
        there would be nothing left to submit later.
        """
        if view in self._views:
            self._views.remove(view)
        projection = self._projections.pop(view, None)
        if projection is not None:
            projection.setParent(None)
            projection.deleteLater()
        if not self._views:
            self.flush()
        return len(self._views)

    # ------------------------------------------------------- the text

    @property
    def dirty(self):
        """Whether the buffer holds edits the model has not been told of."""
        return self._timer.isActive()

    def _touched(self):
        if self._loading:
            return
        self._timer.start()

    def _projection_changed(self, view, position, removed, added):
        if self._applying_projection:
            return
        projection = self._projections.get(view)
        if projection is None:
            return
        inserted = self._range_text(projection, position, added)
        existing = self._range_text(self.document, position, removed)
        # Qt reports block and character formatting changes through the same
        # signal as text changes, with an equal removed/added span. Layout,
        # syntax colour, and focus-mode dimming are projection state; do not
        # turn them into shared text edits or master undo commands.
        if existing == inserted:
            return
        self._origin_view = view
        try:
            self._replace_range(self.document, position, removed, inserted)
        finally:
            self._origin_view = None

    def _master_changed(self, position, removed, added):
        self.revision += 1
        inserted = self._range_text(self.document, position, added)
        self._applying_projection = True
        try:
            for view, projection in tuple(self._projections.items()):
                if view is self._origin_view:
                    continue
                self._replace_range(projection, position, removed, inserted)
        finally:
            self._applying_projection = False

    @staticmethod
    def _range_text(document, position, length):
        if not length:
            return ""
        cursor = QTextCursor(document)
        limit = max(0, document.characterCount() - 1)
        start = min(position, limit)
        end = min(position + length, limit)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        # QTextDocumentFragment.toPlainText() destroys non-breaking spaces.
        # selectedText() retains them and only needs Qt's paragraph markers
        # translated to the newlines the manuscript model stores.
        return cursor.selectedText().translate(PLAIN_TRANSLATION_TABLE)

    @staticmethod
    def _replace_range(document, position, removed, inserted):
        cursor = QTextCursor(document)
        limit = max(0, document.characterCount() - 1)
        start = min(position, limit)
        end = min(position + removed, limit)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(inserted)

    def _replace_projection_text(self, projection, text):
        self._applying_projection = True
        try:
            projection.setPlainText(text)
        finally:
            self._applying_projection = False

    def load(self, text):
        """Take text from the model into the buffer.

        Declines while the buffer is dirty, and that is the whole point: a
        rename, an undo in another window, or a revision restore reaches the
        model while somebody is mid-sentence here, and the sentence is the
        newer of the two. It is written out on the next submit, so the model
        is not left disagreeing for long.
        """
        if self.dirty:
            return False
        # Compared the way the buffer reports its own text, not by raw
        # document content. Raw text separates paragraphs with U+2029, so
        # anything with more than one paragraph never looked equal to the
        # newlines the model holds -- and re-setting text that had not
        # changed threw away the undo history with it.
        if self.text() == text:
            return False
        self._loading = True
        try:
            # Taking text in is not the person editing, so it must not be
            # undoable. Turning undo off clears the history and turning it
            # back on starts a fresh one, which leaves a freshly opened
            # document with nothing to undo -- and the editor's undo
            # button correctly grey.
            self.document.setUndoRedoEnabled(False)
            self.document.setPlainText(text)
            self.document.setUndoRedoEnabled(True)
        finally:
            self._loading = False
        return True

    def settle(self):
        """Forget everything done merely to get the text on screen.

        Loading from the model, then applying fonts and block formats, are
        not the person editing -- but they are edits as far as Qt is
        concerned, so each leaves an undo step and a pending submit
        behind. A freshly opened document must have nothing to undo and
        nothing to write back. Toggling undo off and on is how a
        QTextDocument is made to drop its history.
        """
        self._timer.stop()
        self.document.setUndoRedoEnabled(False)
        self.document.setUndoRedoEnabled(True)

    def submit(self):
        """Write the buffer into the model, if it has anything to say."""
        self._timer.stop()
        if self.index is None or not self.index.isValid():
            return False
        # A persistent index says where the cell is; the model still wants
        # to be handed an ordinary one.
        index = self.model.index(
            self.index.row(), self.index.column(), self.index.parent(),
        )
        text = self.text()
        if text == self.model.data(index):
            return False
        self.model.setData(index, text)
        return True

    def text(self):
        """The buffer's text, read the one way the whole application reads it.

        Asked of the domain rather than of the editor. What plain text means
        for a QTextDocument used to be a constant in textEditView, so this
        service imported a widget module to learn what its own text said.
        """
        return plain_text(self.document)

    def flush(self):
        """Submit now rather than when the timer says so."""
        if self._timer.isActive():
            self._timer.stop()
            return self.submit()
        return False


class DocumentBufferRegistry(QObject):
    """Every open document's buffer, one apiece, for one project.

    Project scope: a window closing is not a document closing, and the text
    a second window is still showing must not go with the first.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buffers = {}

    def __len__(self):
        return len(self._buffers)

    @staticmethod
    def key_for(model, index, column, identifier):
        """What makes two views the same document, or None if unknowable.

        The identity is supplied rather than discovered. The registry could
        read it off the index, but only by way of internalPointer(), which
        is a Python outline item in the outline's own model and raw C++
        internals in the QStandardItemModel ones -- reading it there
        segfaults the interpreter. So whoever knows which model this is
        says what the document is called, and says nothing when the model
        has no notion of one.
        """
        if model is None or index is None or not index.isValid():
            return None
        if identifier is None or identifier == "":
            return None
        return (id(model), str(identifier), column)

    def buffer_for(self, model, index, column, identifier, view=None):
        """The shared buffer for a document, made if this is the first ask."""
        key = self.key_for(model, index, column, identifier)
        if key is None:
            return None
        buffer = self._buffers.get(key)
        if buffer is None:
            buffer = TextBuffer(model, index, column, parent=self)
            self._buffers[key] = buffer
            buffer.load(text_of(model, index))
        if view is not None:
            buffer.attach(view)
        return buffer

    def detach(self, view, buffer):
        """Drop a view, and the buffer once nothing shows it."""
        if buffer is None:
            return
        if buffer.detach(view) == 0:
            for key, value in list(self._buffers.items()):
                if value is buffer:
                    del self._buffers[key]
            buffer.setParent(None)

    def flush(self):
        """Write every pending edit into the models.

        Called before anything that reads the models as though they were
        current: a save, an autosave, a commit, a project close.
        """
        written = 0
        for buffer in tuple(self._buffers.values()):
            try:
                if buffer.flush():
                    written += 1
            except RuntimeError:
                # A buffer whose model went away mid-close has nothing to
                # say and is not a reason to abandon the rest.
                LOGGER.debug("A text buffer could not be flushed.")
        return written

    def forget_all(self):
        """Let every buffer go, the project having closed."""
        self.flush()
        for buffer in tuple(self._buffers.values()):
            buffer.setParent(None)
        self._buffers.clear()


def text_of(model, index):
    """The model's text for a cell, as a string."""
    return as_text(model.data(model.index(
        index.row(), index.column(), index.parent(),
    )))
