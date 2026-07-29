from PyQt5.QtCore import QTimer
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
        self.hide()

        self._refreshTimer = QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(0)
        self._refreshTimer.timeout.connect(self.refresh)
        source_editor.document().contentsChanged.connect(
            self.scheduleRefresh
        )

    def setActive(self, active):
        if active:
            self.refresh()
            self.show()
            self.raise_()
        else:
            self.hide()

    def scheduleRefresh(self):
        if not self.isHidden():
            self._refreshTimer.start()

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

        new_maximum = scrollbar.maximum()
        scrollbar.setValue(round(scroll_ratio * new_maximum))
