import threading
import time

from PyQt5.QtWidgets import qApp

from manuskript.plugins.api import (
    ExtensionDescriptor,
    MarkupAnalysisResult,
    MarkupContribution,
    MarkupMode,
    SemanticRole,
    SemanticSpan,
    TextRange,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.settingsManager import SettingsManager
from manuskript.ui.plugins.markup_profiles import MarkupProfileService
from manuskript.ui.plugins.semantic_markup import (
    MAX_ANALYSIS_UTF16_UNITS,
    _analysis_windows,
)
from manuskript.ui.views.MDEditView import MDEditView


def wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline
        qApp.processEvents()
        time.sleep(0.005)


def result(request, spans=()):
    return MarkupAnalysisResult(
        request.analysis_id,
        request.document_id,
        request.document_revision,
        request.window,
        tuple(spans),
    )


def contribution(analyze, cancel=None, mode=MarkupMode.AUGMENT):
    return MarkupContribution(
        ExtensionDescriptor("example.semantic", "Semantic example"),
        mode,
        analyze,
        cancel,
    )


def editor_with(contribution_value, text):
    registry = PluginRegistry()
    registrar = registry.registrar("example.plugin")
    registrar.register_markup(contribution_value)
    registry.install("example.plugin", registrar.contributions)
    state = MarkupProfileService(registry).create_state()
    if contribution_value.mode is MarkupMode.REPLACE:
        state.set_base(contribution_value.descriptor.id)
    else:
        state.set_additive(contribution_value.descriptor.id, True)
    editor = MDEditView(spellcheck=False, settings=SettingsManager())
    editor.setEnabled(True)
    editor.setPlainText(text)
    editor.setMarkupProfileState(state)
    return editor


def dispose(editor):
    editor.setMarkupProfileState(None)
    editor.dispose()
    editor.close()
    editor.deleteLater()
    qApp.processEvents()


def test_portable_markup_is_batched_and_painted_without_source_mutation():
    requests = []

    def analyze(request):
        requests.append(request)
        start = request.source.index("TODO")
        return result(request, (
            SemanticSpan(
                TextRange(request.window.start + start, 4),
                SemanticRole.HIGHLIGHT,
            ),
        ))

    editor = editor_with(contribution(analyze), "One TODO remains source.")
    try:
        wait_until(lambda: editor._semanticMarkup.spans)
        qApp.processEvents()

        assert editor.toPlainText() == "One TODO remains source."
        assert len(requests) == 1
        assert requests[0].changed_ranges
        assert requests[0].window.length < MAX_ANALYSIS_UTF16_UNITS
        formats = editor.document().firstBlock().layout().formats()
        assert any(value.start == 4 and value.length == 4 for value in formats)
    finally:
        dispose(editor)


def test_rapid_edit_cancels_and_rejects_the_stale_result():
    started = threading.Event()
    release = threading.Event()
    cancelled = []
    requests = []

    def analyze(request):
        requests.append(request)
        if len(requests) == 1:
            started.set()
            assert release.wait(2)
            role = SemanticRole.ERROR
        else:
            role = SemanticRole.STRONG
        return result(request, (
            SemanticSpan(TextRange(request.window.start, 1), role),
        ))

    editor = editor_with(
        contribution(analyze, cancel=lambda value: cancelled.append(value)),
        "old",
    )
    try:
        wait_until(started.is_set)
        editor.setPlainText("newer")
        wait_until(lambda: bool(cancelled))
        release.set()
        wait_until(lambda: len(requests) >= 2)
        wait_until(lambda: (
            editor._semanticMarkup.spans
            and editor._semanticMarkup.spans[0].role is SemanticRole.STRONG
        ))

        assert cancelled == [requests[0].analysis_id]
        assert requests[-1].document_revision == editor._semanticMarkup.revision
        assert editor.toPlainText() == "newer"
    finally:
        release.set()
        dispose(editor)


def test_several_keystrokes_become_one_changed_line_request():
    requests = []

    def analyze(request):
        requests.append(request)
        return result(request)

    editor = editor_with(
        contribution(analyze),
        "First line.\nSecond line.\nThird line.",
    )
    try:
        wait_until(lambda: bool(requests))
        requests.clear()
        cursor = editor.textCursor()
        cursor.setPosition(editor.toPlainText().index("Second") + 6)
        editor.setTextCursor(cursor)
        for character in " typed":
            editor.insertPlainText(character)

        wait_until(lambda: bool(requests))
        time.sleep(0.2)
        qApp.processEvents()

        assert len(requests) == 1
        assert "Second typed line." == requests[0].source.strip()
        assert requests[0].window.length < len(
            editor.toPlainText().encode("utf-16-le")
        ) // 2
    finally:
        dispose(editor)


def test_long_source_is_split_on_utf16_boundaries():
    source = "🪶" + ("word " * 15000)
    windows = _analysis_windows(source, 0, len(source.encode("utf-16-le")) // 2)

    assert len(windows) >= 2
    assert all(
        window.length <= MAX_ANALYSIS_UTF16_UNITS
        for window, _fragment, _changed in windows
    )
    assert windows[0][0].start == 0
    assert windows[-1][0].end == len(source.encode("utf-16-le")) // 2
    assert "".join(fragment for _window, fragment, _changed in windows) == source


def test_semantic_span_after_non_bmp_text_uses_utf16_offsets_in_qt():
    def analyze(request):
        assert request.source == "🪶TODO"
        return result(request, (
            SemanticSpan(TextRange(2, 4), SemanticRole.STRONG),
        ))

    editor = editor_with(contribution(analyze), "🪶TODO")
    try:
        wait_until(lambda: editor._semanticMarkup.spans)
        qApp.processEvents()

        formats = editor.document().firstBlock().layout().formats()
        assert any(value.start == 2 and value.length == 4 for value in formats)
        assert editor.toPlainText() == "🪶TODO"
    finally:
        dispose(editor)


def test_replacement_markup_can_exclude_delimiters_from_plain_projection():
    def analyze(request):
        return result(request, (
            SemanticSpan(
                TextRange(request.window.start, 3),
                SemanticRole.MARKUP,
                exclude_from_plain_text=True,
            ),
            SemanticSpan(
                TextRange(request.window.start + 4, 4),
                SemanticRole.MARKUP,
                exclude_from_plain_text=True,
            ),
        ))

    editor = editor_with(
        contribution(analyze, mode=MarkupMode.REPLACE),
        "[b]x[/b]",
    )
    try:
        wait_until(lambda: len(editor._semanticMarkup.spans) == 2)

        assert editor.clearedFormatForStats("[b]x[/b]") == "x"
        assert editor.toPlainText() == "[b]x[/b]"
    finally:
        dispose(editor)
