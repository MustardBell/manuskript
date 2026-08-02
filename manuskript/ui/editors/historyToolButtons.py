"""Undo and redo controls floating at the left of the editor.

They act on the text in this pane. Outline structure has its own history,
reached from the Edit menu and from Ctrl+Z inside the outline views, because a
control sitting in a text editor should reverse editing and nothing else.
"""

from PyQt5.QtWidgets import QStyle

from manuskript.ui.editors.editorOverlayButton import (
    EditorOverlayToolButton,
    overlay_icon,
)


class HistoryToolButton(EditorOverlayToolButton):
    """One direction of the active text document's undo history."""

    def __init__(self, history, redo=False, parent=None):
        super().__init__(parent)
        self.history = history
        self.isRedo = redo
        self.setObjectName(
            "redoToolButton" if redo else "undoToolButton")
        self.setIcon(overlay_icon(
            ("edit-redo",) if redo else ("edit-undo",),
            QStyle.SP_ArrowForward if redo else QStyle.SP_ArrowBack,
        ))
        self.setToolTip(
            self.tr("Redo typing") if redo else self.tr("Undo typing")
        )
        if history is None:
            self.setEnabled(False)
            return
        self.clicked.connect(history.redo if redo else history.undo)
        history.changed.connect(self.sync)
        self.sync()

    def sync(self):
        if self.history is None:
            return
        self.setEnabled(
            self.history.canRedo() if self.isRedo else self.history.canUndo()
        )
