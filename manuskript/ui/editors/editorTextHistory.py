"""Undo state for the text being edited in one editor pane.

Deliberately not the project's structure stack. These controls sit inside a
text editor, so they undo typing; deleting a scene is undone from the outline,
where the scene lives. Mixing the two behind one button would make it
impossible to know what a click was about to reverse.
"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import qApp


class EditorTextHistory(QObject):
    """Track the document of whichever text editor in this pane has focus.

    A pane can hold several editors at once — the folder "text" view stacks
    one per child item — so the active document is resolved on demand rather
    than bound once.
    """

    changed = pyqtSignal()

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner
        self._hooked = set()
        qApp.focusChanged.connect(self._focusChanged)

    # ------------------------------------------------------------------

    def editors(self):
        """Every text editor this pane owns, canonical one first."""
        found = [getattr(self._owner, "txtRedacText", None)]
        found.extend(getattr(self._owner, "txtEdits", ()) or ())
        return [editor for editor in found if editor is not None]

    def activeEditor(self):
        focused = qApp.focusWidget()
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
        document = editor.document()
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
        """Report a document's availability changes, once per document."""
        key = id(document)
        if key in self._hooked:
            return
        self._hooked.add(key)
        document.undoAvailable.connect(self._emitChanged)
        document.redoAvailable.connect(self._emitChanged)

    def _focusChanged(self, _old, _new):
        self._emitChanged()

    def _emitChanged(self, *_args):
        self.changed.emit()
