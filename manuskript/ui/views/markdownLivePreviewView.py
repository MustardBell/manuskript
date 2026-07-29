from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import (
    QTextCursor,
)
from PyQt5.QtWidgets import QFrame, QTextEdit

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.editors.markdownProjection import (
    MarkdownProjectionMap,
    MarkdownProjectionRenderer,
)
from manuskript.ui.highlighters import MarkdownHighlighter


class MarkdownProjectionHighlighter(MarkdownHighlighter):
    """Highlight source syntax only in the projection's active block."""

    def highlightBlock(self, text):
        active_range = self.editor.activeProjectionRange
        block = self.currentBlock()
        if (
            active_range is not None
            and block.position() <= active_range[0]
            < block.position() + block.length()
        ):
            super().highlightBlock(text)


class MarkdownLivePreviewView(QTextEdit):
    """Rendered Markdown projection with one canonical source line exposed."""

    def __init__(self, source_editor):
        super().__init__(source_editor.viewport())
        self._sourceEditor = source_editor
        self._active = False
        self._dirty = True
        self._building = False
        self._activeSourceBlock = 0
        self._positionMap = MarkdownProjectionMap([])
        self.activeProjectionRange = None
        self._renderer = MarkdownProjectionRenderer(source_editor)

        # MarkdownHighlighter's editor-facing dependencies.
        self.settings = source_editor.settings
        self.spellcheck = source_editor.spellcheck
        self._dict = source_editor._dict
        self._defaultFontSize = source_editor._defaultFontSize
        self._noFocusMode = False
        self._fromTheme = source_editor._fromTheme
        self._themeData = source_editor._themeData

        self.setObjectName("markdownLivePreviewView")
        self.setFrameShape(QFrame.NoFrame)
        self.setAcceptRichText(False)
        self.setUndoRedoEnabled(False)
        if source_editor._autoResize:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hide()

        self.highlighter = MarkdownProjectionHighlighter(self)
        self._refreshTimer = QTimer(self)
        self._refreshTimer.setSingleShot(True)
        self._refreshTimer.setInterval(0)
        self._refreshTimer.timeout.connect(self.rebuild)

        source_editor.document().contentsChanged.connect(
            self.scheduleRebuild
        )
        source_editor.cursorPositionChanged.connect(
            self.sourceCursorChanged
        )
        self.cursorPositionChanged.connect(
            self._syncSourceCursorFromProjection
        )

    @property
    def presentationMode(self):
        return MarkdownPresentationMode.FORMATTED_SOURCE

    def setActive(self, active):
        self._active = bool(active)
        if active:
            self._activeSourceBlock = (
                self._sourceEditor.textCursor().blockNumber()
            )
            self._dirty = True
            self.show()
            self.raise_()
            self.refreshIfNeeded()
        else:
            self._syncSourceCursorFromProjection()
            self.hide()

    def scheduleRebuild(self):
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

    def sourceCursorChanged(self):
        if self._building or not self._active:
            return
        source_block = self._sourceEditor.textCursor().blockNumber()
        if source_block != self._activeSourceBlock:
            self._activeSourceBlock = source_block
            self.scheduleRebuild()

    def setProjectionWidth(self, width):
        if width <= 0:
            return
        document = self.document()
        if document.textWidth() != width:
            document.setTextWidth(width)
            if self._active and self._sourceEditor._autoResize:
                self._sourceEditor.sizeChange()

    def rebuild(self):
        if not self._active:
            return

        self._building = True
        try:
            scrollbar = self.verticalScrollBar()
            old_maximum = scrollbar.maximum()
            old_value = scrollbar.value()
            scroll_ratio = (
                old_value / old_maximum
                if old_maximum
                else 0
            )

            source_cursor = self._sourceEditor.textCursor()
            source_block = source_cursor.block()
            self._activeSourceBlock = source_block.blockNumber()

            self.highlighter.setDocument(None)
            document = self.document()
            (
                self.activeProjectionRange,
                self._positionMap,
            ) = self._renderer.render(
                document,
                source_block,
            )
            self._setProjectionCursorFromSource()

            self.highlighter.setDocument(document)
            self.highlighter.rehighlight()
            self._dirty = False
            self.setProjectionWidth(self.viewport().width())
            if self._sourceEditor._autoResize:
                self._sourceEditor.sizeChange()

            new_maximum = scrollbar.maximum()
            scrollbar.setValue(round(scroll_ratio * new_maximum))
        finally:
            self._building = False

    def _syncSourceCursorFromProjection(self):
        if self._building or not self._active:
            return

        projection_cursor = self.textCursor()
        source_position = self._sourcePositionForProjectionPosition(
            projection_cursor.position()
        )
        source_anchor = self._sourcePositionForProjectionPosition(
            projection_cursor.anchor()
        )
        if source_position is None or source_anchor is None:
            return

        source_block_number = (
            self._sourceEditor.document()
            .findBlock(source_position)
            .blockNumber()
        )
        block_changed = (
            source_block_number != self._activeSourceBlock
        )
        self._activeSourceBlock = source_block_number

        source_cursor = QTextCursor(self._sourceEditor.document())
        source_cursor.setPosition(source_anchor)
        source_cursor.setPosition(
            source_position,
            QTextCursor.KeepAnchor,
        )
        self._sourceEditor.setTextCursor(source_cursor)

        if block_changed:
            self.scheduleRebuild()

    def _sourcePositionForProjectionPosition(self, position):
        active_start, active_end = self.activeProjectionRange
        if active_start <= position <= active_end:
            source_block = (
                self._sourceEditor.document()
                .findBlockByNumber(self._activeSourceBlock)
            )
            return source_block.position() + min(
                max(0, position - active_start),
                len(source_block.text()),
            )

        return self._positionMap.source_position_at(position)

    def keyPressEvent(self, event):
        self._syncSourceCursorFromProjection()
        source_document = self._sourceEditor.document()
        old_block_count = source_document.blockCount()
        old_revision = source_document.revision()
        old_block_number = (
            self._sourceEditor.textCursor().blockNumber()
        )
        self._sourceEditor.keyPressEvent(event)
        new_block_number = (
            self._sourceEditor.textCursor().blockNumber()
        )
        if (
            source_document.blockCount() == old_block_count
            and new_block_number == old_block_number
            and new_block_number == self._activeSourceBlock
        ):
            self._refreshTimer.stop()
            if source_document.revision() == old_revision:
                self._setProjectionCursorFromSource()
            else:
                self._updateActiveSourceBlock()
        else:
            self._activeSourceBlock = new_block_number
            self._dirty = True
            self.rebuild()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self._syncSourceCursorFromProjection()

    def _updateActiveSourceBlock(self):
        if self.activeProjectionRange is None:
            self.rebuild()
            return

        self._building = True
        try:
            source_block = self._sourceEditor.textCursor().block()
            self.highlighter.setDocument(None)
            self.activeProjectionRange = (
                self._renderer.replace_active_source(
                    self.document(),
                    self.activeProjectionRange,
                    source_block,
                )
            )
            self._positionMap = MarkdownProjectionMap.from_document(
                self.document(),
                self._sourceEditor.toPlainText(),
            )
            self._setProjectionCursorFromSource()
            self.highlighter.setDocument(self.document())
            self.highlighter.rehighlightBlock(self.textCursor().block())
            self._dirty = False
        finally:
            self._building = False

    def _setProjectionCursorFromSource(self):
        if self.activeProjectionRange is None:
            return
        active_start, active_end = self.activeProjectionRange
        source_cursor = self._sourceEditor.textCursor()
        source_block = source_cursor.block()
        source_block_start = source_block.position()
        source_anchor_block = self._sourceEditor.document().findBlock(
            source_cursor.anchor()
        )
        source_anchor_offset = (
            source_cursor.anchor() - source_block_start
            if source_anchor_block == source_block
            else source_cursor.positionInBlock()
        )
        projection_cursor = QTextCursor(self.document())
        projection_cursor.setPosition(
            min(active_start + source_anchor_offset, active_end)
        )
        projection_cursor.setPosition(
            min(
                active_start + source_cursor.positionInBlock(),
                active_end,
            ),
            QTextCursor.KeepAnchor,
        )
        self.setTextCursor(projection_cursor)

    def inputMethodEvent(self, event):
        commit = event.commitString()
        if commit:
            self._syncSourceCursorFromProjection()
            cursor = self._sourceEditor.textCursor()
            cursor.insertText(commit)
            self._sourceEditor.setTextCursor(cursor)
            self._refreshTimer.stop()
            self._updateActiveSourceBlock()
            event.accept()
            return
        super().inputMethodEvent(event)
