from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QTextDocument
from PyQt5.QtWidgets import QFrame, QTextBrowser


class MarkdownReadingView(QTextBrowser):
    """Read-only projection of an MDEditView's source document."""

    def __init__(self, source_editor):
        super().__init__(source_editor.viewport())
        self._sourceEditor = source_editor
        self.setObjectName("markdownReadingView")
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        if source_editor._autoResize:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hide()
        self._active = False
        self._dirty = True

        self._refreshTimer = QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(0)
        self._refreshTimer.timeout.connect(self.refresh)
        source_editor.document().contentsChanged.connect(
            self.scheduleRefresh
        )

    def setActive(self, active):
        self._active = bool(active)
        if active:
            self.show()
            self.raise_()
            self.refreshIfNeeded()
        else:
            self.hide()

    def scheduleRefresh(self):
        self._dirty = True
        if self._active and self._sourceEditor.isVisible():
            self._refreshTimer.start()

    def refreshIfNeeded(self):
        if (
            self._active
            and self._dirty
            and self._sourceEditor.isVisible()
        ):
            self._refreshTimer.start()

    def setProjectionWidth(self, width):
        if width <= 0:
            return
        document = self.document()
        if document.textWidth() != width:
            document.setTextWidth(width)
            if self._active:
                self._sourceEditor.sizeChange()

    def refresh(self):
        scrollbar = self.verticalScrollBar()
        old_maximum = scrollbar.maximum()
        old_value = scrollbar.value()
        scroll_ratio = (
            old_value / old_maximum
            if old_maximum
            else 0
        )

        document = self.document()
        document.setDefaultFont(self._sourceEditor.font())
        document.setMarkdown(
            self._sourceEditor.toPlainText(),
            QTextDocument.MarkdownDialectGitHub,
        )
        self._dirty = False
        self.setProjectionWidth(self.viewport().width())
        self._sourceEditor.sizeChange()

        new_maximum = scrollbar.maximum()
        scrollbar.setValue(round(scroll_ratio * new_maximum))
