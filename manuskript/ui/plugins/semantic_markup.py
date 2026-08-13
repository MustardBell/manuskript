"""Batched, revisioned host rendering for portable markup contributions."""

import bisect
import logging
import threading
import uuid

from dataclasses import dataclass

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QFont, QTextCharFormat, QTextCursor

from manuskript.domain.text import plain_text
from manuskript.plugins.api import (
    MarkupAnalysisRequest,
    MarkupAnalysisResult,
    SemanticRole,
    TextRange,
)


LOGGER = logging.getLogger(__name__)
ANALYSIS_DEBOUNCE_MS = 140
MAX_ANALYSIS_UTF16_UNITS = 32 * 1024


class _JobSignals(QObject):
    finished = pyqtSignal(object)


@dataclass(frozen=True)
class _BatchOutcome:
    revision: int
    cancelled: bool
    results: tuple
    errors: tuple


class _AnalysisJob(QRunnable):
    def __init__(self, revision, calls, cancelled):
        super().__init__()
        self.revision = revision
        self.calls = tuple(calls)
        self.cancelled = cancelled
        self.signals = _JobSignals()

    def run(self):
        results = []
        errors = []
        for contribution, request in self.calls:
            if self.cancelled.is_set():
                break
            try:
                result = contribution.analyze(request)
                _validate_result(request, result)
            except Exception as error:
                errors.append((contribution, error))
            else:
                results.append((contribution.descriptor.id, result))
        self.signals.finished.emit(_BatchOutcome(
            self.revision,
            self.cancelled.is_set(),
            tuple(results),
            tuple(errors),
        ))


class _CancellationJob(QRunnable):
    def __init__(self, calls):
        super().__init__()
        self.calls = tuple(calls)

    def run(self):
        for contribution, analysis_id in self.calls:
            cancel = contribution.cancel_analysis
            if cancel is None:
                continue
            try:
                cancel(analysis_id)
            except Exception:
                LOGGER.exception(
                    "Markup plugin %s failed to cancel analysis %s.",
                    contribution.descriptor.id,
                    analysis_id,
                )


class SemanticMarkupSession(QObject):
    """Own one editor projection's portable semantic analysis.

    Source and its revision remain in Manuskript. Plugins receive bounded
    UTF-16 windows only after typing pauses; they return semantic roles, while
    this session maps those roles through the editor's current host theme.
    """

    changed = pyqtSignal()

    def __init__(
            self, editor, contributions, report_error=None, parent=None,
            thread_pool=None):
        super().__init__(parent or editor)
        self.editor = editor
        self.contributions = tuple(contributions)
        self.reportError = report_error or (lambda _contribution, _error: None)
        self.threadPool = thread_pool or QThreadPool.globalInstance()
        self.documentId = str(uuid.uuid4())
        self._document = None
        self._documentConnection = None
        self._lastSource = ""
        self._localRevision = 0
        self._dirtyStart = None
        self._dirtyEnd = None
        self._spans = {
            contribution.descriptor.id: ()
            for contribution in self.contributions
        }
        self._running = False
        self._activeCancellation = None
        self._activeRequests = ()
        self._tasks = set()
        self._disposed = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(ANALYSIS_DEBOUNCE_MS)
        self.timer.timeout.connect(self._start)
        editor.documentReplaced.connect(self._bind_document)
        self._bind_document()

    @property
    def spans(self):
        return tuple(
            span
            for contribution_spans in self._spans.values()
            for span in contribution_spans
        )

    @property
    def revision(self):
        buffer = getattr(self.editor, "_buffer", None)
        return (
            int(buffer.revision)
            if buffer is not None
            else self._localRevision
        )

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.timer.stop()
        self._cancel_active()
        try:
            self.editor.documentReplaced.disconnect(self._bind_document)
        except (RuntimeError, TypeError):
            pass
        self._disconnect_document()
        self.editor = None

    def _bind_document(self):
        if self._disposed:
            return
        self._disconnect_document()
        self._document = self.editor.document()
        self._lastSource = plain_text(self._document)
        self._documentConnection = self._document.contentsChange.connect(
            self._document_changed
        )
        self._dirtyStart = 0
        self._dirtyEnd = _utf16_length(self._lastSource)
        self.timer.start(0)

    def _disconnect_document(self):
        document = self._document
        connection = self._documentConnection
        self._documentConnection = None
        self._document = None
        if document is not None and connection is not None:
            try:
                document.contentsChange.disconnect(connection)
            except (RuntimeError, TypeError):
                pass

    def _document_changed(self, position, removed, added):
        if self._disposed or self._document is None:
            return
        source = plain_text(self._document)
        if source == self._lastSource:
            return
        self._lastSource = source
        if getattr(self.editor, "_buffer", None) is None:
            self._localRevision += 1
        self._shift_spans(position, removed, added)
        changed_end = position + added
        self._dirtyStart = (
            position
            if self._dirtyStart is None
            else min(self._dirtyStart, position)
        )
        self._dirtyEnd = (
            changed_end
            if self._dirtyEnd is None
            else max(self._dirtyEnd, changed_end)
        )
        self._cancel_active()
        self.timer.start()

    def _shift_spans(self, position, removed, added):
        removed_end = position + removed
        delta = added - removed
        for contribution_id, spans in tuple(self._spans.items()):
            shifted = []
            for span in spans:
                value = span.range
                if value.end <= position:
                    shifted.append(span)
                elif value.start >= removed_end:
                    shifted.append(type(span)(
                        TextRange(value.start + delta, value.length),
                        span.role,
                        span.message,
                        span.exclude_from_plain_text,
                    ))
            self._spans[contribution_id] = tuple(shifted)

    def _cancel_active(self):
        cancelled = self._activeCancellation
        if cancelled is None or cancelled.is_set():
            return
        cancelled.set()
        calls = tuple(self._activeRequests)
        if calls:
            self.threadPool.start(_CancellationJob(calls))

    def _start(self):
        if self._disposed or self._document is None:
            return
        if self._running:
            return
        if self._dirtyStart is None:
            return
        source = plain_text(self._document)
        revision = self.revision
        start, end = self._dirtyStart, self._dirtyEnd
        self._dirtyStart = None
        self._dirtyEnd = None
        windows = _analysis_windows(source, start, end)
        cancelled = threading.Event()
        calls = []
        active = []
        for contribution in self.contributions:
            for window, fragment, changed in windows:
                analysis_id = str(uuid.uuid4())
                request = MarkupAnalysisRequest(
                    analysis_id,
                    self.documentId,
                    revision,
                    window,
                    fragment,
                    (changed,),
                )
                calls.append((contribution, request))
                active.append((contribution, analysis_id))
        if not calls:
            return
        job = _AnalysisJob(revision, calls, cancelled)
        self._running = True
        self._activeCancellation = cancelled
        self._activeRequests = tuple(active)
        self._tasks.add(job)

        def finished(outcome):
            self._tasks.discard(job)
            self._running = False
            if self._activeCancellation is cancelled:
                self._activeCancellation = None
                self._activeRequests = ()
            if not self._disposed:
                self._accept(outcome)
                if self._dirtyStart is not None:
                    self.timer.start(0)

        job.signals.finished.connect(finished)
        self.threadPool.start(job)

    def _accept(self, outcome):
        if outcome.cancelled or outcome.revision != self.revision:
            return
        for contribution, error in outcome.errors:
            self.reportError(contribution, error)
        for contribution_id, result in outcome.results:
            existing = self._spans.get(contribution_id, ())
            window = result.window
            retained = tuple(
                span for span in existing
                if span.range.end <= window.start
                or span.range.start >= window.end
            )
            self._spans[contribution_id] = tuple(sorted(
                retained + result.spans,
                key=lambda span: (span.range.start, span.range.length),
            ))
        self.changed.emit()

    def highlight_block(self, highlighter, _text):
        block = highlighter.currentBlock()
        block_start = block.position()
        block_end = block_start + _utf16_length(block.text())
        for span in self.spans:
            start = max(block_start, span.range.start)
            end = min(block_end, span.range.end)
            if end <= start:
                continue
            relative = start - block_start
            value = QTextCharFormat(highlighter.format(relative))
            _apply_role(highlighter, value, span)
            highlighter.setFormat(relative, end - start, value)

    def plain_text(self, text):
        """Project cached delimiter decisions without mutating source."""

        text = str(text)
        if text != self._lastSource:
            return None
        excluded = _merged_ranges(tuple(
            span.range for span in self.spans
            if span.exclude_from_plain_text
        ))
        if not excluded:
            return None
        offsets = _utf16_offsets(text)
        result = text
        for value in sorted(excluded, key=lambda item: item.start, reverse=True):
            start = _python_index(offsets, value.start)
            end = _python_index(offsets, value.end)
            result = result[:start] + result[end:]
        return result


def _validate_result(request, result):
    if not isinstance(result, MarkupAnalysisResult):
        raise TypeError("Markup analyzers must return MarkupAnalysisResult.")
    if (
        result.analysis_id != request.analysis_id
        or result.document_id != request.document_id
        or result.document_revision != request.document_revision
        or result.window != request.window
    ):
        raise ValueError("Markup result identity does not match its request.")


def _analysis_windows(source, dirty_start, dirty_end):
    source = str(source)
    offsets = _utf16_offsets(source)
    total = offsets[-1]
    dirty_start = min(max(0, int(dirty_start)), total)
    dirty_end = min(max(dirty_start, int(dirty_end)), total)
    py_start = _python_index(offsets, dirty_start)
    py_end = _python_index(offsets, dirty_end)
    line_start = source.rfind("\n", 0, py_start) + 1
    next_newline = source.find("\n", py_end)
    line_end = len(source) if next_newline < 0 else next_newline + 1
    if not source:
        empty = TextRange(0, 0)
        return ((empty, "", empty),)

    windows = []
    cursor = line_start
    while cursor < line_end:
        limit_units = offsets[cursor] + MAX_ANALYSIS_UTF16_UNITS
        candidate = bisect.bisect_right(offsets, limit_units) - 1
        candidate = max(cursor + 1, min(candidate, line_end))
        if candidate < line_end:
            boundary = source.rfind("\n", cursor + 1, candidate + 1)
            if boundary >= cursor + 1:
                candidate = boundary + 1
        window_start = offsets[cursor]
        window_end = offsets[candidate]
        changed_start = min(
            window_end, max(window_start, dirty_start)
        )
        changed_end = min(
            window_end, max(changed_start, dirty_end)
        )
        windows.append((
            TextRange(window_start, window_end - window_start),
            source[cursor:candidate],
            TextRange(changed_start, changed_end - changed_start),
        ))
        cursor = candidate
    return tuple(windows)


def _utf16_offsets(value):
    offsets = [0]
    position = 0
    for character in str(value):
        position += 2 if ord(character) > 0xFFFF else 1
        offsets.append(position)
    return offsets


def _utf16_length(value):
    return _utf16_offsets(value)[-1]


def _python_index(offsets, position):
    index = bisect.bisect_left(offsets, position)
    if index >= len(offsets) or offsets[index] != position:
        raise ValueError("UTF-16 offset splits a surrogate pair.")
    return index


def _merged_ranges(values):
    merged = []
    for value in sorted(values, key=lambda item: (item.start, item.end)):
        if not merged or value.start > merged[-1].end:
            merged.append(value)
            continue
        previous = merged[-1]
        merged[-1] = TextRange(
            previous.start,
            max(previous.end, value.end) - previous.start,
        )
    return tuple(merged)


def _apply_role(highlighter, value, span):
    role = span.role
    if role is SemanticRole.MARKUP:
        value.setForeground(QBrush(highlighter.markupColor))
        value.setFontFamily("Monospace")
    elif role is SemanticRole.EMPHASIS:
        value.setFontItalic(True)
    elif role in (SemanticRole.STRONG, SemanticRole.HEADING):
        value.setFontWeight(QFont.Bold)
    elif role is SemanticRole.CODE:
        value.setFontFamily("Monospace")
    elif role is SemanticRole.LINK:
        value.setForeground(QBrush(highlighter.linkColor))
        value.setFontUnderline(True)
    elif role in (SemanticRole.COMMENT, SemanticRole.STRING):
        value.setFontItalic(True)
    elif role in (
        SemanticRole.KEYWORD,
        SemanticRole.NUMBER,
        SemanticRole.VARIABLE,
        SemanticRole.SUCCESS,
    ):
        value.setFontWeight(QFont.DemiBold)
    elif role is SemanticRole.HIGHLIGHT:
        palette = highlighter.editor.palette()
        value.setBackground(palette.highlight())
        value.setForeground(palette.highlightedText())
    elif role is SemanticRole.WARNING:
        value.setUnderlineStyle(QTextCharFormat.DashUnderline)
        value.setFontWeight(QFont.DemiBold)
    elif role is SemanticRole.ERROR:
        value.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        value.setUnderlineColor(highlighter.spellingErrorColor)
    if span.message:
        value.setToolTip(span.message)
