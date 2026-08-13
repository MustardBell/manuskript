"""Undo state for the text being edited in one editor pane.

Deliberately not the project's structure stack. These controls sit inside a
text editor, so they undo typing; deleting a scene is undone from the outline,
where the scene lives. Mixing the two behind one button would make it
impossible to know what a click was about to reverse.
"""

from PyQt5.QtCore import QObject, Qt, pyqtSignal


class EditorTextHistory(QObject):
    """Track the document of whichever text editor in this pane has focus.

    A pane can hold several editors at once — the folder "text" view stacks
    one per child item — so the active document is resolved on demand rather
    than bound once.
    """

    changed = pyqtSignal()

    def __init__(self, owner, focus_source=None, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._focus_source = focus_source
        if focus_source is not None:
            focus_source.subscribe(self._focusChanged)

    # ------------------------------------------------------------------

    def editors(self):
        """Every text editor this pane owns, canonical one first."""
        found = [getattr(self._owner, "txtRedacText", None)]
        found.extend(getattr(self._owner, "txtEdits", ()) or ())
        editors = [editor for editor in found if editor is not None]
        for editor in editors:
            self._followDocumentSwaps(editor)
        return editors

    def _followDocumentSwaps(self, editor):
        """Notice when an editor starts showing a different document.

        An editor's document is no longer fixed for its lifetime: joining
        or leaving a shared project buffer swaps it. The availability
        signals were hooked on whichever document was current when these
        buttons were first asked, so after a swap they reported on a
        document nobody was looking at and the buttons stayed grey while
        undo was available.
        """
        signal = getattr(editor, "documentReplaced", None)
        if signal is None:
            return
        try:
            signal.connect(self._emitChanged, Qt.UniqueConnection)
        except TypeError:
            pass

    def activeEditor(self):
        focused = (
            self._focus_source.focused_widget
            if self._focus_source is not None
            else None
        )
        editors = self.editors()
        while focused is not None:
            if focused in editors:
                return focused
            focused = focused.parentWidget()
        return editors[0] if editors else None

    def document(self):
        editor = self.activeEditor()
        if editor is None:
            return None
        buffer = getattr(editor, "_buffer", None)
        document = buffer.document if buffer is not None else editor.document()
        self._hook(document)
        return document

    def canUndo(self):
        document = self.document()
        return bool(document is not None and document.isUndoAvailable())

    def canRedo(self):
        document = self.document()
        return bool(document is not None and document.isRedoAvailable())

    def undo(self):
        document = self.document()
        if document is not None:
            document.undo()

    def redo(self):
        document = self.document()
        if document is not None:
            document.redo()

    # ------------------------------------------------------------------

    def _hook(self, document):
        """Report a document's availability changes, once per document.

        Connected uniquely rather than remembered by id(). A Python id is
        an address and addresses are reused, so once documents come and go
        -- which they do as soon as two views share one buffer, since
        attaching and releasing swaps documents -- a fresh document could
        land on a freed address, be taken for one already hooked, and then
        never report anything. Its undo button stayed grey while undo was
        perfectly available.
        """
        for signal in (document.undoAvailable, document.redoAvailable):
            try:
                signal.connect(self._emitChanged, Qt.UniqueConnection)
            except TypeError:
                # Already connected, which is exactly what was wanted.
                pass

    def _focusChanged(self, _old, _new):
        self._emitChanged()

    def _emitChanged(self, *_args):
        self.changed.emit()

    def dispose(self):
        if self._focus_source is not None:
            self._focus_source.unsubscribe(self._focusChanged)
        self._focus_source = None
        self._owner = None
