from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QStackedWidget

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.views.markdownReadingView import MarkdownReadingView


class MarkdownEditorHost(QStackedWidget):
    """Own the mutually exclusive views of one Markdown document."""

    currentViewChanged = pyqtSignal(object)

    def __init__(self, source_editor, parent=None):
        super().__init__(parent)
        self.setObjectName("markdownEditorHost")
        self.setFrameShape(QFrame.NoFrame)
        self.sourceEditor = source_editor
        self.readingView = None
        self.addWidget(source_editor)
        source_editor.setPresentationHost(self)

    @property
    def canonicalEditor(self):
        return self.sourceEditor

    def setPresentationMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        target = self._viewForMode(mode)
        previous = self.currentWidget()

        if previous is not target and hasattr(previous, "setActive"):
            previous.setActive(False)

        self.setCurrentWidget(target)
        if hasattr(target, "setActive"):
            target.setActive(True)
        self.setFocusProxy(target)
        self.currentViewChanged.emit(target)
        return target if target is not self.sourceEditor else None

    def _viewForMode(self, mode):
        if mode is MarkdownPresentationMode.READING:
            return self._ensureReadingView()
        return self.sourceEditor

    def _ensureReadingView(self):
        if self.readingView is None:
            self.readingView = MarkdownReadingView(
                self.sourceEditor,
                self,
            )
            self.addWidget(self.readingView)
            self.sourceEditor.readingView = self.readingView
        return self.readingView
