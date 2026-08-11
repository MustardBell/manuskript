from unittest.mock import MagicMock

import pytest
from PyQt5.QtCore import QPoint, Qt, QUrl, pyqtSignal
from PyQt5.QtGui import (
    QFont,
    QTextCharFormat,
    QTextCursor,
)
from PyQt5.QtWidgets import qApp, QWidget
from PyQt5.QtTest import QSignalSpy, QTest

from manuskript.enums import Outline
from manuskript.domain.reference_index import ReferenceSuggestion
from manuskript.models.outlineItem import outlineItem
from manuskript.settingsManager import SettingsManager
from manuskript.ui.editors.markdownEditorHost import MarkdownEditorHost
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationBinding,
    MarkdownPresentationDefaults,
    MarkdownPresentationMode,
    MarkdownPresentationState,
)
from manuskript.ui.highlighters import MarkdownHighlighter
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.views.text_editor_context import TextEditorContext


def make_context(settings, **commands):
    return TextEditorContext(
        settings=settings,
        reload_fonts=MagicMock(),
        create_character=MagicMock(),
        create_plot=MagicMock(),
        create_world_item=MagicMock(),
        invoke_outline_command=MagicMock(),
        **commands,
    )


def host_editor(editor, width=480, height=360):
    host = MarkdownEditorHost(editor)
    host.resize(width, height)
    return host


def wait_until(condition, timeout=2000):
    """Wait for a condition rather than for a fixed number of ms.

    A keystroke delivered to a widget is processed through the event
    loop, and how long that takes depends on what else the machine is
    doing. A fixed wait passes on an idle machine and fails on a busy
    one, which is a race in the test rather than a fault in the editor.
    """
    waited = 0
    while waited < timeout:
        qApp.processEvents()
        if condition():
            return True
        QTest.qWait(10)
        waited += 10
    return condition()


def format_at(editor, position):
    block = editor.document().findBlock(position)
    position_in_block = position - block.position()
    for format_range in block.layout().formats():
        if (
            format_range.start
            <= position_in_block
            < format_range.start + format_range.length
        ):
            return format_range.format
    return QTextCharFormat()


def test_markdown_presentation_mode_defines_display_policy():
    assert MarkdownPresentationMode.SOURCE.is_editable
    assert not MarkdownPresentationMode.SOURCE.renders_markdown
    assert not MarkdownPresentationMode.SOURCE.reveals_active_block

    assert MarkdownPresentationMode.FORMATTED_SOURCE.is_editable
    assert MarkdownPresentationMode.FORMATTED_SOURCE.renders_markdown
    assert not (
        MarkdownPresentationMode.FORMATTED_SOURCE.reveals_active_block
    )

    assert MarkdownPresentationMode.LIVE_PREVIEW.is_editable
    assert MarkdownPresentationMode.LIVE_PREVIEW.renders_markdown
    assert MarkdownPresentationMode.LIVE_PREVIEW.reveals_active_block

    assert MarkdownPresentationMode.CLEAN_EDITING.is_editable
    assert MarkdownPresentationMode.CLEAN_EDITING.renders_markdown
    assert not MarkdownPresentationMode.CLEAN_EDITING.reveals_active_block

    assert not MarkdownPresentationMode.READING.is_editable
    assert MarkdownPresentationMode.READING.renders_markdown
    assert not MarkdownPresentationMode.READING.reveals_active_block


def test_markdown_presentation_mode_normalizes_persisted_values():
    assert MarkdownPresentationMode.from_value(
        "LIVE_PREVIEW"
    ) is MarkdownPresentationMode.LIVE_PREVIEW

    with pytest.raises(
        ValueError,
        match="Unknown Markdown presentation mode",
    ):
        MarkdownPresentationMode.from_value("wysiwyg")


def test_leaf_presentation_state_emits_only_real_transitions():
    state = MarkdownPresentationState(
        MarkdownPresentationMode.FORMATTED_SOURCE
    )
    transitions = []
    state.modeChanged.connect(transitions.append)

    state.set_mode(MarkdownPresentationMode.SOURCE)
    state.set_mode("source")
    state.set_mode("reading")

    assert transitions == [
        MarkdownPresentationMode.SOURCE,
        MarkdownPresentationMode.READING,
    ]


def test_presentation_binding_moves_one_control_surface_between_leaves():
    enabled = []
    attached = []
    modes = []
    allowed_modes = []
    binding = MarkdownPresentationBinding(
        set_enabled=enabled.append,
        state_changed=attached.append,
        sync_mode=modes.append,
        sync_allowed_modes=allowed_modes.append,
    )
    first = MarkdownPresentationState()
    second = MarkdownPresentationState(MarkdownPresentationMode.SOURCE)

    binding.attach(first)
    first.set_mode(MarkdownPresentationMode.READING)
    binding.attach(second)
    modes.clear()
    first.set_mode(MarkdownPresentationMode.LIVE_PREVIEW)
    second.set_mode(MarkdownPresentationMode.FORMATTED_SOURCE)

    assert enabled == [True, True]
    assert attached == [first, second]
    assert modes == [MarkdownPresentationMode.FORMATTED_SOURCE]
    assert allowed_modes[-1] == tuple(MarkdownPresentationMode)


def test_presentation_binding_detaches_and_routes_mode_intent():
    enabled = []
    attached = []
    binding = MarkdownPresentationBinding(
        set_enabled=enabled.append,
        state_changed=attached.append,
        sync_mode=lambda _mode: None,
        sync_allowed_modes=lambda _modes: None,
    )
    state = MarkdownPresentationState()
    binding.attach(state)

    binding.set_mode(MarkdownPresentationMode.LIVE_PREVIEW)
    binding.dispose()
    state.set_mode(MarkdownPresentationMode.READING)

    assert state.mode is MarkdownPresentationMode.READING
    assert enabled == [True, False]
    assert attached == [state, None]


def test_presentation_defaults_repair_an_unknown_persisted_value():
    settings = SettingsManager()
    settings.textEditor["markdownDefaultMode"] = "wysiwyg"

    mode = MarkdownPresentationDefaults.load(settings)

    assert mode is MarkdownPresentationMode.FORMATTED_SOURCE
    assert (
        settings.textEditor["markdownDefaultMode"]
        == "formatted-source"
    )


def test_live_preview_uses_the_canonical_editor_without_a_host():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )

    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )

    assert (
        editor.presentationMode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert editor.highlighter.document() is editor.document()


def test_reading_mode_requires_an_explicit_editor_host():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )

    with pytest.raises(RuntimeError, match="MarkdownEditorHost"):
        editor.setPresentationMode(
            MarkdownPresentationMode.READING
        )

    assert (
        editor.presentationMode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )


def test_editor_mode_switch_preserves_source_selection_and_undo_state():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host_editor(editor)
    editor.setPlainText("before **selected** after")
    cursor = editor.textCursor()
    start = editor.toPlainText().index("selected")
    cursor.setPosition(start)
    cursor.setPosition(
        start + len("selected"),
        QTextCursor.KeepAnchor,
    )
    editor.setTextCursor(cursor)

    editor.setPresentationMode(MarkdownPresentationMode.READING)

    assert editor.isReadOnly()
    assert editor.toPlainText() == "before **selected** after"
    assert editor.textCursor().selectedText() == "selected"
    assert not editor.document().isUndoAvailable()

    editor.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)

    assert not editor.isReadOnly()
    assert editor.textCursor().selectedText() == "selected"


def test_leaf_presentation_state_synchronizes_its_document_views():
    settings = SettingsManager()
    state = MarkdownPresentationState()
    first = MDEditView(spellcheck=False, settings=settings)
    second = MDEditView(spellcheck=False, settings=settings)
    host_editor(first)
    host_editor(second)
    first.setPresentationState(state)
    second.setPresentationState(state)

    state.set_mode("reading")

    assert first.presentationMode is MarkdownPresentationMode.READING
    assert second.presentationMode is MarkdownPresentationMode.READING
    assert first.isReadOnly()
    assert second.isReadOnly()


def test_presentation_host_uses_source_for_live_and_sibling_for_reading():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("# Heading\n\nBody with **emphasis**.")
    editor.setEnabled(True)
    host.show()
    try:
        editor.setPresentationMode(
            MarkdownPresentationMode.LIVE_PREVIEW
        )
        qApp.processEvents()

        assert host.currentWidget() is editor
        assert editor.isVisible()
        assert host.count() == 1

        editor.setPresentationMode(
            MarkdownPresentationMode.READING
        )
        qApp.processEvents()

        reading = editor.readingView
        assert reading.parent() is host
        assert host.currentWidget() is reading
        assert reading.isVisible()
        assert editor.isHidden()
        assert host.count() == 2

        editor.setPresentationMode(
            MarkdownPresentationMode.FORMATTED_SOURCE
        )
        qApp.processEvents()

        assert host.currentWidget() is editor
        assert editor.isVisible()
        assert reading.isHidden()
    finally:
        host.hide()


def test_page_wizard_replaces_an_already_active_live_view_and_applies_once():
    class Wizard(QWidget):
        applyRequested = pyqtSignal(str)

        def __init__(self):
            super().__init__()
            self.loaded = None

        def load_source(self, source):
            self.loaded = source

    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("canonical source")
    editor.document().clearUndoRedoStacks()
    editor.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)

    host.setPageWizardFactory(Wizard)
    wizard = host.currentWidget()

    assert isinstance(wizard, Wizard)
    assert wizard.loaded == "canonical source"
    assert editor.toPlainText() == "canonical source"

    wizard.applyRequested.emit("structured source")

    assert editor.toPlainText() == "structured source"
    editor.undo()
    assert editor.toPlainText() == "canonical source"


def test_auxiliary_markdown_editor_has_no_leaf_presentation_state():
    settings = SettingsManager()
    state = MarkdownPresentationState()
    context = make_context(settings)
    editor = MDEditView(spellcheck=False, settings=settings)
    editor.set_text_editor_context(context)

    state.set_mode("reading")

    assert (
        editor.presentationMode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert editor.readingView is None
    assert not editor.isReadOnly()


def test_detaching_leaf_state_restores_formatted_source():
    settings = SettingsManager()
    state = MarkdownPresentationState()
    editor = MDEditView(spellcheck=False, settings=settings)
    host_editor(editor)
    editor.setPresentationState(state)
    state.set_mode("reading")

    editor.setPresentationState(None)

    assert (
        editor.presentationMode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert not editor.isReadOnly()


def test_html_display_editor_remains_read_only_in_editable_modes():
    editor = MDEditView(
        html="<h1>Folder</h1>",
        spellcheck=False,
        settings=SettingsManager(),
    )

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)

    assert editor.isReadOnly()


def test_source_mode_shows_markup_without_rendering_emphasis():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**bold** and *italic*")

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)
    editor.highlighter.rehighlight()
    qApp.processEvents()

    opening_bold = format_at(editor, 0)
    bold_text = format_at(editor, 2)
    italic_text = format_at(
        editor,
        editor.toPlainText().index("italic"),
    )
    assert opening_bold.foreground().color().alpha() != 0
    assert bold_text.fontWeight() != QFont.Bold
    assert not italic_text.fontItalic()


def test_formatted_source_shows_markup_and_rendered_emphasis():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setPlainText("**bold** and *italic*")

    editor.setPresentationMode(
        MarkdownPresentationMode.FORMATTED_SOURCE
    )
    editor.highlighter.rehighlight()
    qApp.processEvents()

    opening_bold = format_at(editor, 0)
    bold_text = format_at(editor, 2)
    italic_text = format_at(
        editor,
        editor.toPlainText().index("italic"),
    )
    assert opening_bold.foreground().color().alpha() != 0
    assert bold_text.fontWeight() == QFont.Bold
    assert italic_text.fontItalic()


def test_live_preview_formats_canonical_source_and_reveals_active_markup():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    source_document = editor.document()
    editor.setPlainText("**first**\n**second**")
    second_block = editor.document().findBlockByNumber(1)
    cursor = editor.textCursor()
    cursor.setPosition(second_block.position() + 2)
    editor.setTextCursor(cursor)

    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        first_marker = format_at(editor, 0)
        first_text = format_at(editor, 2)
        second_marker = format_at(editor, second_block.position())

        assert host.currentWidget() is editor
        assert editor.document() is source_document
        assert editor.toPlainText() == "**first**\n**second**"
        assert first_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert first_marker.foreground().color().alpha() == 0
        assert first_marker.fontStretch() == 1
        assert first_text.fontWeight() == QFont.Bold
        assert not second_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert editor.highlighter.document() is source_document
    finally:
        host.hide()


def test_clean_editing_hides_markup_including_the_active_block():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    source = "**bold** and [[Characters/Mara|Mara]]"
    editor.setPlainText(source)

    editor.setPresentationMode(MarkdownPresentationMode.CLEAN_EDITING)
    host.show()
    try:
        qApp.processEvents()
        bold_marker = format_at(editor, 0)
        link_marker = format_at(editor, source.index("[["))
        bold_text = format_at(editor, source.index("bold"))

        assert host.currentWidget() is editor
        assert editor.toPlainText() == source
        assert bold_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert link_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert bold_text.fontWeight() == QFont.Bold
        assert not MarkdownPresentationMode.CLEAN_EDITING.reveals_active_block
    finally:
        host.hide()


def test_live_preview_rehighlights_old_and_new_active_blocks():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("**first**\n**second**")
    second_block = editor.document().findBlockByNumber(1)
    cursor = editor.textCursor()
    cursor.setPosition(second_block.position() + 2)
    editor.setTextCursor(cursor)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        first_marker = format_at(editor, 0)
        second_marker = format_at(editor, second_block.position())
        assert first_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert not second_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )

        cursor.setPosition(2)
        editor.setTextCursor(cursor)
        qApp.processEvents()

        first_marker = format_at(editor, 0)
        second_marker = format_at(editor, second_block.position())
        assert not first_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert second_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
    finally:
        host.hide()


def test_live_preview_projects_wikilink_display_without_mutating_source():
    editor = MDEditView(spellcheck=False, settings=SettingsManager())
    host = host_editor(editor)
    source = (
        "Meet [[Characters/Olena|Олену]].\n"
        "Then [[Places/Kyiv]]."
    )
    editor.setPlainText(source)
    second = editor.document().findBlockByNumber(1)
    cursor = editor.textCursor()
    cursor.setPosition(second.position() + 8)
    editor.setTextCursor(cursor)
    editor.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)
    host.show()
    try:
        qApp.processEvents()
        opening = source.index("[[")
        target = source.index("Characters/Olena")
        display = source.index("Олену")
        second_opening = source.index("[[", opening + 2)

        assert editor.toPlainText() == source
        assert format_at(editor, opening).property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert format_at(editor, target).property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert not format_at(editor, display).property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert format_at(editor, display).fontUnderline()
        assert not format_at(editor, second_opening).property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
    finally:
        host.hide()


def test_wikilinks_in_code_are_neither_projected_nor_clickable():
    editor = MDEditView(spellcheck=False, settings=SettingsManager())
    host = host_editor(editor)
    source = "```\n[[CodeExample]]\n```\n[[Actual]]"
    editor.setPlainText(source)
    editor.setPresentationMode(MarkdownPresentationMode.LIVE_PREVIEW)
    host.show()
    try:
        qApp.processEvents()
        editor.getClickRects()

        code_target = format_at(editor, source.index("CodeExample"))
        actual_target = format_at(editor, source.index("Actual"))
        wikilink_targets = [
            item.texts[1]
            for item in editor.clickRects
            if item.regex is editor.wikilinkRegex
        ]

        assert not code_target.fontUnderline()
        assert actual_target.fontUnderline()
        assert wikilink_targets == ["Actual"]
        assert editor.toPlainText() == source
    finally:
        host.hide()


def test_wikilink_completion_replaces_only_the_target_source_span():
    editor = MDEditView(spellcheck=False, settings=SettingsManager())
    suggestions = (ReferenceSuggestion(
        "mara", "Characters/Mara", "Mara", "Characters/Mara.md"
    ),)
    editor.set_text_editor_context(make_context(
        editor.settings,
        complete_wikilink=lambda prefix: suggestions
        if prefix == "Mar" else (),
    ))
    editor.setPlainText("See [[Mar")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)

    menu = editor.buildWikilinkCompletionMenu()

    assert menu is not None
    assert editor.toPlainText() == "See [[Mar"
    assert menu.actions()[0].text() == "Mara — Characters/Mara"
    menu.actions()[0].trigger()
    assert editor.toPlainText() == "See [[Characters/Mara]]"
    assert editor.textCursor().position() == len("See [[Characters/Mara")


def test_live_preview_keeps_list_markers_position_stable():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("- First item\n- Second item")
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        second_block = editor.document().findBlockByNumber(1)
        marker = format_at(editor, second_block.position())
        assert editor.toPlainText() == "- First item\n- Second item"
        assert not marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
    finally:
        host.hide()


def test_live_preview_formats_heading_and_html_underline_off_line():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText(
        "# Heading\n\nA <u>stable underline</u>."
    )
    cursor = editor.textCursor()
    cursor.setPosition(
        editor.document().findBlockByNumber(1).position()
    )
    editor.setTextCursor(cursor)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        heading_marker = format_at(editor, 0)
        opening_tag = editor.toPlainText().index("<u>")
        underline_text = editor.toPlainText().index("stable underline")
        tag_format = format_at(editor, opening_tag)

        assert editor.toPlainText() == (
            "# Heading\n\nA <u>stable underline</u>."
        )
        assert heading_marker.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert tag_format.property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert tag_format.foreground().color().alpha() == 0
        assert tag_format.fontStretch() == 1
        assert format_at(editor, underline_text).fontUnderline()
    finally:
        host.hide()


def test_live_preview_edits_the_canonical_source_and_preserves_undo():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("**first**\nsecond")
    editor.setEnabled(True)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        assert host.currentWidget() is editor
        QTest.keyClicks(editor, "x")
        wait_until(
            lambda: editor.toPlainText() == "**first**\nsecondx"
        )

        assert editor.toPlainText() == "**first**\nsecondx"

        editor.undo()
        wait_until(
            lambda: editor.toPlainText() == "**first**\nsecond"
        )

        assert editor.toPlainText() == "**first**\nsecond"
    finally:
        host.hide()


def test_live_preview_click_activates_the_source_block_without_mutation():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("**first**\n**second**")
    editor.setEnabled(True)
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        source_before = editor.toPlainText()
        content_changes = QSignalSpy(editor.document().contentsChange)
        click_cursor = editor.document().find("first")
        click_cursor.setPosition(click_cursor.selectionStart() + 2)
        QTest.mouseClick(
            editor.viewport(),
            Qt.LeftButton,
            pos=editor.cursorRect(click_cursor).center(),
        )
        qApp.processEvents()

        assert editor.textCursor().blockNumber() == 0
        assert editor.toPlainText() == source_before
        assert len(content_changes) == 0
        assert not format_at(editor, 0).property(
            MarkdownHighlighter.MarkupHiddenProperty
        )
        assert format_at(
            editor,
            editor.document().findBlockByNumber(1).position(),
        ).property(MarkdownHighlighter.MarkupHiddenProperty)
    finally:
        host.hide()


def test_live_preview_repeated_clicks_preserve_content_and_scroll():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    source_lines = [
        "Paragraph {} has **stable prose** and <u>underlining</u>.".format(
            number
        )
        for number in range(80)
    ]
    source = "\n\n".join(source_lines)
    editor.setPlainText(source)
    editor.setEnabled(True)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        source_before = editor.toPlainText()
        undo_before = editor.document().isUndoAvailable()
        content_changes = QSignalSpy(editor.document().contentsChange)
        scrollbar = editor.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum() // 2)
        qApp.processEvents()
        viewport = editor.viewport().rect()
        click_points = (
            QPoint(viewport.width() // 3, viewport.height() // 3),
            QPoint(viewport.width() // 2, viewport.height() // 2),
            QPoint(
                viewport.width() * 2 // 3,
                viewport.height() * 2 // 3,
            ),
        )

        for click_point in click_points * 3:
            scroll_before = scrollbar.value()
            QTest.mouseClick(
                editor.viewport(),
                Qt.LeftButton,
                pos=click_point,
            )
            qApp.processEvents()

            assert editor.toPlainText() == source_before
            assert len(content_changes) == 0
            assert (
                editor.document().isUndoAvailable()
                == undo_before
            )
            assert scrollbar.value() == scroll_before

        assert not editor.isReadOnly()
        assert editor.toPlainText() == source_before
    finally:
        host.hide()


def test_live_preview_click_focuses_and_edits_the_canonical_model(
        MWEmptyProject):
    window = MWEmptyProject
    window_was_visible = window.isVisible()
    window.resize(900, 700)
    window.show()
    window.raise_()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    source = (
        "# Model-backed chapter\n\n"
        "A paragraph with **rendered emphasis**.\n\n"
        "Another paragraph remains canonical."
    )
    item = outlineItem(title="Click safety", _type="md")
    item.setData(Outline.text, source)
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    source_editor = window.mainEditor.currentEditor().txtRedacText
    source_editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    try:
        qApp.processEvents()
        assert (
            source_editor._presentationHost.currentWidget()
            is source_editor
        )
        target = source_editor.document().find("rendered emphasis")
        target.setPosition(
            target.selectionStart() + len("rendered")
        )
        expected_click_position = (
            source.index("rendered emphasis") + len("rendered")
        )

        # Synthetic clicks do not request focus on every offscreen platform
        # plugin. Make the real focus transfer explicit, then exercise the
        # click and its cursor mapping.
        source_editor.setFocus(Qt.MouseFocusReason)
        QTest.mouseClick(
            source_editor.viewport(),
            Qt.LeftButton,
            pos=source_editor.cursorRect(target).center(),
        )
        QTest.qWait(50)
        assert (
            source_editor.textCursor().position()
            == expected_click_position
        )

        assert source_editor.toPlainText() == source
        assert item.data(Outline.text) == source
        assert window.workspaceFocus.markup_target is source_editor

        insertion_position = source_editor.textCursor().position()
        # QTest sends synthetic key events to the widget supplied here.
        # Naming the click-routed editor avoids a second application-global
        # focus lookup racing deferred Qt events.
        QTest.keyClicks(source_editor, "X")
        QTest.qWait(50)
        edited_source = (
            source[:insertion_position]
            + "X"
            + source[insertion_position:]
        )
        assert source_editor.toPlainText() == edited_source
        source_editor.submit()
        assert item.data(Outline.text) == edited_source

        source_editor.undo()
        qApp.processEvents()
        source_editor.submit()
        assert source_editor.toPlainText() == source
        assert item.data(Outline.text) == source

        source_editor.setPresentationMode(
            MarkdownPresentationMode.READING
        )
        qApp.processEvents()
        assert (
            source_editor._presentationHost.currentWidget()
            is source_editor.readingView
        )
        assert source_editor.readingView.toPlainText() == (
            "Model-backed chapter\n"
            "A paragraph with rendered emphasis.\n"
            "Another paragraph remains canonical."
        )
    finally:
        window.mainEditor.closeAllTabs()
        if not window_was_visible:
            window.hide()


def test_live_preview_selection_routes_formatting_to_source():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("first\nsecond")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.End)
    editor.setTextCursor(cursor)
    editor.setPresentationMode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    host.show()
    try:
        qApp.processEvents()
        start = editor.toPlainText().index("second")
        selection = QTextCursor(editor.document())
        selection.setPosition(start)
        selection.setPosition(
            start + len("second"),
            QTextCursor.KeepAnchor,
        )
        editor.setTextCursor(selection)

        editor.bold()
        qApp.processEvents()

        assert editor.toPlainText() == "first\n**second**"
    finally:
        host.hide()


def test_reading_mode_is_a_rendered_projection_of_untouched_source():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    source_document = editor.document()
    source = (
        "# Heading\n\n"
        "Some **bold**, *italic*, and <u>underlined</u> text.\n\n"
        "- first\n"
        "- second"
    )
    editor.setPlainText(source)

    editor.setPresentationMode(MarkdownPresentationMode.READING)
    host.show()
    try:
        qApp.processEvents()

        assert editor.document() is source_document
        assert editor.toPlainText() == source
        assert not editor.readingView.isHidden()
        assert editor.readingView.isReadOnly()
        assert editor.readingView.toPlainText() == (
            "Heading\n"
            "Some bold, italic, and underlined text.\n"
            "first\n"
            "second"
        )
        rendered_html = editor.readingView.toHtml()
        assert "<ul" in rendered_html
        assert "font-weight:600" in rendered_html
        assert "text-decoration: underline" in rendered_html
    finally:
        host.hide()


def test_reading_projection_renders_wikilink_display_and_routes_its_target():
    editor = MDEditView(spellcheck=False, settings=SettingsManager())
    open_wikilink = MagicMock(return_value=True)
    completions = (MagicMock(),)
    host = host_editor(editor)
    source = "Meet [[Characters/Olena|Олену]] in [[Places/Kyiv]]."
    editor.setPlainText(source)
    activated = QSignalSpy(editor.wikilinkActivated)

    editor.setPresentationMode(MarkdownPresentationMode.READING)
    host.show()
    try:
        assert wait_until(
            lambda: editor.readingView.toPlainText()
            == "Meet Олену in Places/Kyiv."
        )

        assert editor.toPlainText() == source
        assert editor.readingView.toPlainText() == (
            "Meet Олену in Places/Kyiv."
        )
        assert "[[" not in editor.readingView.toHtml()

        editor.set_text_editor_context(make_context(
            editor.settings,
            open_wikilink=open_wikilink,
            complete_wikilink=lambda _prefix: completions,
        ))
        editor.readingView._anchorClicked(
            QUrl("manuskript:Characters/Olena")
        )
        assert list(activated[0]) == ["Characters/Olena"]
        open_wikilink.assert_called_once_with("Characters/Olena")
        assert editor.wikilinkCompletions("char") == completions
    finally:
        host.hide()


def test_reading_projection_refreshes_when_source_changes():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("**first**")
    editor.setPresentationMode(MarkdownPresentationMode.READING)
    host.show()
    try:
        qApp.processEvents()
        editor.document().setPlainText("*second*")
        qApp.processEvents()

        assert editor.toPlainText() == "*second*"
        assert editor.readingView.toPlainText() == "second"
        assert "font-style:italic" in editor.readingView.toHtml()
    finally:
        host.hide()


def test_leaving_reading_mode_restores_the_same_editable_document():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host_editor(editor)
    source_document = editor.document()
    editor.setPlainText("editable")
    editor.setPresentationMode(MarkdownPresentationMode.READING)

    editor.setPresentationMode(MarkdownPresentationMode.SOURCE)

    assert editor.document() is source_document
    assert editor.toPlainText() == "editable"
    assert editor.readingView.isHidden()
    assert not editor.isReadOnly()


def test_reading_projection_is_lazy_for_hidden_editor():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host = host_editor(editor)
    editor.setPlainText("# Deferred")

    editor.setPresentationMode(MarkdownPresentationMode.READING)

    assert editor.readingView is not None
    assert editor.readingView.toPlainText() == ""

    host.show()
    try:
        qApp.processEvents()
        assert editor.readingView.toPlainText() == "Deferred"
    finally:
        host.hide()


def test_reading_suspends_and_restores_source_highlighting():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    host_editor(editor)
    source_document = editor.document()

    editor.setPresentationMode(MarkdownPresentationMode.READING)
    assert editor.highlighter.document() is None

    editor.setPresentationMode(
        MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert editor.highlighter.document() is source_document


def test_auto_resizing_reading_projection_has_no_nested_scrollbar():
    editor = MDEditView(
        spellcheck=False,
        autoResize=True,
        settings=SettingsManager(),
    )
    host = host_editor(editor, width=480, height=100)
    editor.setPlainText("# Heading\n\nA short paragraph.")
    editor.setPresentationMode(MarkdownPresentationMode.READING)
    host.show()
    try:
        qApp.processEvents()
        assert (
            editor.readingView.verticalScrollBarPolicy()
            == Qt.ScrollBarAlwaysOff
        )
        assert host.minimumHeight() > 0
    finally:
        host.hide()
