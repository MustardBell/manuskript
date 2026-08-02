"""Undo and redo controls floating at the left of the editor.

These act on the project's structure stack, not on the text being typed. The
text editors keep their own undo, which is why these live in their own cluster
at the opposite end of the overlay strip from the view controls.
"""

from PyQt5.QtWidgets import QStyle

from manuskript.ui.editors.editorOverlayButton import (
    EditorOverlayToolButton,
    overlay_icon,
)


class HistoryToolButton(EditorOverlayToolButton):
    """One direction of the project undo stack."""

    def __init__(self, stack, redo=False, parent=None):
        super().__init__(parent)
        self.stack = stack
        self.isRedo = redo
        self.setObjectName(
            "redoToolButton" if redo else "undoToolButton")
        self.setIcon(overlay_icon(
            ("edit-redo",) if redo else ("edit-undo",),
            QStyle.SP_ArrowForward if redo else QStyle.SP_ArrowBack,
        ))
        if stack is None:
            self.setEnabled(False)
            self.setToolTip(self._label(""))
            return
        self.clicked.connect(stack.redo if redo else stack.undo)
        if redo:
            stack.canRedoChanged.connect(self.setEnabled)
            stack.redoTextChanged.connect(self.syncLabel)
            self.setEnabled(stack.canRedo())
            self.syncLabel(stack.redoText())
        else:
            stack.canUndoChanged.connect(self.setEnabled)
            stack.undoTextChanged.connect(self.syncLabel)
            self.setEnabled(stack.canUndo())
            self.syncLabel(stack.undoText())

    def syncLabel(self, command_text):
        """Name the action that will actually happen, not just its direction."""
        self.setToolTip(self._label(command_text))

    def _label(self, command_text):
        if command_text:
            return (
                self.tr("Redo {}") if self.isRedo else self.tr("Undo {}")
            ).format(command_text)
        return self.tr("Nothing to redo") if self.isRedo \
            else self.tr("Nothing to undo")
