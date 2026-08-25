from PyQt5.QtCore import QTimer, Qt, QUrl
from PyQt5.QtGui import QTextDocument
from PyQt5.QtWidgets import QFrame, QTextBrowser

from manuskript.domain.assertion_dsl import render_story_markdown


class MarkdownReadingView(QTextBrowser):
    """Read-only projection of an MDEditView's source document."""

    def __init__(self, source_editor, parent=None):
        super().__init__(parent)
        self._sourceEditor = source_editor
        self.setObjectName("markdownReadingView")
        self.setFrameShape(QFrame.NoFrame)
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        if source_editor._autoResize:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._active = False
        self._dirty = True
        self._renderer = None

        self._refreshTimer = QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(0)
        self._refreshTimer.timeout.connect(self.refresh)

    def setActive(self, active):
        self._active = bool(active)
        if active:
            host = self.parentWidget()
            if (
                self._dirty
                and host is not None
                and host.isVisible()
            ):
                # A QStackedWidget changes its current page before every
                # native backend reports that child as visible. Scheduling
                # through ``isVisible()`` can therefore expose an empty
                # Reading page for one event turn on macOS. The host is the
                # stable exposure boundary: when it is already visible, a
                # completed mode switch must also have completed the first
                # projection. Hidden hosts retain the intentional lazy path.
                self._refreshTimer.stop()
                self.refresh()
            else:
                self.refreshIfNeeded()

    def setRenderer(self, renderer):
        if renderer is self._renderer:
            return
        self._renderer = renderer
        self.scheduleRefresh()

    def scheduleRefresh(self):
        self._dirty = True
        if self._active and self.isVisible():
            self._refreshTimer.start()

    def refreshIfNeeded(self):
        if (
            self._active
            and self._dirty
            and self.isVisible()
        ):
            self._refreshTimer.start()

    def setProjectionWidth(self, width):
        if width <= 0:
            return
        document = self.document()
        if document.textWidth() != width:
            document.setTextWidth(width)
            if self._active and self._sourceEditor._autoResize:
                self._sourceEditor.sizeChange()

    def resizeEvent(self, event):
        QTextBrowser.resizeEvent(self, event)
        self.setProjectionWidth(self.viewport().width())

    def showEvent(self, event):
        QTextBrowser.showEvent(self, event)
        self.refreshIfNeeded()

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
        source = self._sourceEditor.toPlainText()
        if self._renderer is None:
            document.setBaseUrl(QUrl())
            projected = (
                render_story_markdown(source)
                if self._sourceEditor.storyProjectionEnabled()
                else source
            )
            document.setMarkdown(
                projected,
                QTextDocument.MarkdownDialectGitHub,
            )
        else:
            rendered = self._renderer.render(source)
            document.setBaseUrl(QUrl(rendered.base_url))
            document.setHtml(rendered.html)
        self._dirty = False
        self.setProjectionWidth(self.viewport().width())
        if self._sourceEditor._autoResize:
            self._sourceEditor.sizeChange()

        new_maximum = scrollbar.maximum()
        scrollbar.setValue(round(scroll_ratio * new_maximum))
