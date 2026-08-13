import re

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import (
    QColor,
    QKeyEvent,
    QTextCharFormat,
    QTextCursor,
)
from PyQt5.QtWidgets import qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.plugins.api import (
    ExtensionDescriptor,
    MarkupMode,
    NativeMarkupContribution,
)
from manuskript.plugins.qt import (
    MarkupBehavior,
    MarkupHighlighterExtension,
    PluginHighlighter,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.settingsManager import SettingsManager
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.highlighters import (
    BasicHighlighter,
    MarkdownHighlighter,
)
from manuskript.ui.plugins.markup_profiles import MarkupProfileService
from manuskript.ui.views.MDEditView import MDEditView


class BBCodeHighlighter(PluginHighlighter):
    def doHighlightBlock(self, text):
        markup = QTextCharFormat()
        markup.setForeground(QColor("magenta"))
        for match in re.finditer(r"\[/?[a-z]+\]", text):
            self.setFormat(
                match.start(),
                match.end() - match.start(),
                markup,
            )


class BBCodeBehavior(MarkupBehavior):
    def command(self, editor, command, *arguments):
        if command != "bold":
            return False
        editor.insertFormattingMarkup("[b]", "[/b]")
        return True

    def plain_text(self, editor, text, remove_comments=False):
        return re.sub(r"\[/?[a-z]+\]", "", text)


class TodoHighlight(MarkupHighlighterExtension):
    def __init__(self, calls):
        self.calls = calls

    def highlight_block(self, highlighter, text):
        self.calls.append(text)
        start = text.find("TODO")
        if start >= 0:
            marked = QTextCharFormat()
            marked.setBackground(QColor("yellow"))
            highlighter.setFormat(start, 4, marked)


def install_markup(registry, plugin_id, contribution):
    registrar = registry.registrar(plugin_id)
    registrar.register_native_markup(contribution)
    registry.install(plugin_id, registrar.contributions)


def replacement_contribution(behavior=True):
    return NativeMarkupContribution(
        descriptor=ExtensionDescriptor(
            id="example.bbcode",
            name="BBCode",
        ),
        mode=MarkupMode.REPLACE,
        highlighter_factory=BBCodeHighlighter,
        behavior_factory=(
            BBCodeBehavior if behavior else None
        ),
    )


def make_editor():
    editor = MDEditView(
        spellcheck=False,
        settings=SettingsManager(),
    )
    editor.setEnabled(True)
    return editor


def select_text(editor, text):
    start = editor.toPlainText().index(text)
    cursor = editor.textCursor()
    cursor.setPosition(start)
    cursor.setPosition(
        start + len(text),
        QTextCursor.KeepAnchor,
    )
    editor.setTextCursor(cursor)


def dispose_editor(editor):
    editor.setMarkupProfileState(None)
    editor.interactionRectUpdateTimer.stop()
    editor.close()
    editor.deleteLater()
    qApp.processEvents()


def test_replacement_profile_owns_highlight_commands_and_plain_text():
    registry = PluginRegistry()
    install_markup(
        registry,
        "example.plugin",
        replacement_contribution(),
    )
    service = MarkupProfileService(registry)
    state = service.create_state()
    state.set_base("example.bbcode")
    editor = make_editor()
    editor.setMarkupProfileState(state)
    editor.setPlainText("[b]word[/b]")
    select_text(editor, "word")

    editor.bold()

    assert isinstance(editor.highlighter, BBCodeHighlighter)
    assert editor.toPlainText() == "word"
    assert editor.clearedFormatForStats("[b]word[/b]") == "word"
    assert not isinstance(editor.highlighter, MarkdownHighlighter)
    dispose_editor(editor)


def test_replacement_without_behavior_never_falls_back_to_markdown():
    registry = PluginRegistry()
    install_markup(
        registry,
        "example.plugin",
        replacement_contribution(behavior=False),
    )
    state = MarkupProfileService(registry).create_state()
    state.set_base("example.bbcode")
    editor = make_editor()
    editor.setMarkupProfileState(state)
    editor.setPlainText("- item")
    editor.moveCursor(QTextCursor.End)

    editor.keyPressEvent(
        QKeyEvent(
            QEvent.KeyPress,
            Qt.Key_Return,
            Qt.NoModifier,
        )
    )
    editor.bold()
    editor.clearFormat()

    assert editor.toPlainText() == "- item\n"
    assert editor.clearedFormatForStats("literal **stars**") == (
        "literal **stars**"
    )
    dispose_editor(editor)


def test_additive_profile_layers_onto_markdown_highlighter():
    calls = []
    registry = PluginRegistry()
    install_markup(
        registry,
        "example.todo",
        NativeMarkupContribution(
            descriptor=ExtensionDescriptor(
                id="example.todo.highlight",
                name="TODO highlight",
            ),
            mode=MarkupMode.AUGMENT,
            highlighter_factory=lambda _editor: TodoHighlight(calls),
        ),
    )
    state = MarkupProfileService(registry).create_state()
    state.set_additive("example.todo.highlight", True)
    editor = make_editor()
    editor.setMarkupProfileState(state)
    editor.setPlainText("Markdown **and** TODO")
    editor.highlighter.rehighlight()
    qApp.processEvents()

    assert isinstance(editor.highlighter, MarkdownHighlighter)
    assert "Markdown **and** TODO" in calls
    dispose_editor(editor)


def test_registry_refresh_falls_back_from_removed_replacement():
    registry = PluginRegistry()
    install_markup(
        registry,
        "example.plugin",
        replacement_contribution(),
    )
    service = MarkupProfileService(registry)
    state = service.create_state()
    state.set_base("example.bbcode")
    changes = []
    state.changed.connect(lambda: changes.append(True))

    registry.remove_plugin("example.plugin")
    service.refresh()

    assert state.base_id == "markdown"
    assert changes == [True]


def test_invalid_replacement_isolated_behind_plain_highlighter():
    registry = PluginRegistry()
    install_markup(
        registry,
        "example.broken",
        NativeMarkupContribution(
            descriptor=ExtensionDescriptor(
                id="example.broken.markup",
                name="Broken markup",
            ),
            mode=MarkupMode.REPLACE,
            highlighter_factory=lambda _editor: object(),
        ),
    )
    errors = []
    service = MarkupProfileService(
        registry,
        report_error=lambda *values: errors.append(values),
    )
    state = service.create_state()
    state.set_base("example.broken.markup")
    editor = make_editor()

    editor.setMarkupProfileState(state)

    assert type(editor.highlighter) is BasicHighlighter
    assert errors
    dispose_editor(editor)


def test_markup_profile_is_independent_per_editor_leaf(
        MWEmptyProject):
    window = MWEmptyProject
    registry = window.pluginRuntime.registry
    install_markup(
        registry,
        "example.profile-test",
        replacement_contribution(),
    )
    window.pluginUi.markupProfiles.refresh()
    first_item = outlineItem(title="BBCode", _type="md")
    second_item = outlineItem(title="Markdown", _type="md")
    first_item.setData(Outline.text, "[b]First[/b]")
    second_item.setData(Outline.text, "**Second**")
    window.projectRuntime.models.outline.appendItem(first_item)
    window.projectRuntime.models.outline.appendItem(second_item)
    try:
        window.mainEditor.setCurrentModelIndex(
            window.projectRuntime.models.outline.indexFromItem(first_item),
            newTab=True,
        )
        first = window.mainEditor.currentEditor()
        first.markupProfile.set_base("example.bbcode")

        assert isinstance(
            first.txtRedacText.highlighter,
            BBCodeHighlighter,
        )
        assert (
            first.markdownPresentation.allowed_modes
            == (
                MarkdownPresentationMode.SOURCE,
                MarkdownPresentationMode.FORMATTED_SOURCE,
            )
        )
        assert not window.actMarkdownReading.isEnabled()
        first.markdownPresentation.set_mode(
            MarkdownPresentationMode.READING
        )
        assert (
            first.markdownPresentation.mode
            is MarkdownPresentationMode.FORMATTED_SOURCE
        )

        window.mainEditor.setCurrentModelIndex(
            window.projectRuntime.models.outline.indexFromItem(second_item),
            newTab=True,
        )
        second = window.mainEditor.currentEditor()

        assert second.markupProfile.base_id == "markdown"
        assert isinstance(
            second.txtRedacText.highlighter,
            MarkdownHighlighter,
        )
        assert first.markupProfile.base_id == "example.bbcode"

        registry.remove_plugin("example.profile-test")
        window.pluginUi.markupProfiles.refresh()

        assert first.markupProfile.base_id == "markdown"
        assert isinstance(
            first.txtRedacText.highlighter,
            MarkdownHighlighter,
        )
    finally:
        registry.remove_plugin("example.profile-test")
        window.pluginUi.markupProfiles.refresh()
        window.mainEditor.closeAllTabs()
