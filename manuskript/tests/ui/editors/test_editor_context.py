import importlib
from unittest.mock import patch


class _declining:
    def enter(self, request):
        return None

from PyQt5.QtWidgets import qApp

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)

main_editor_module = importlib.import_module(
    "manuskript.ui.editors.mainEditor"
)


def test_opened_editor_tab_inherits_project_context(MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)

    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()
    settings = window.projectRuntime.settingsManager

    assert editor.editor_context is window.mainEditor.editor_context
    assert editor.outline_context is editor.editor_context.outline_views
    assert editor.corkView.outline_context is editor.outline_context
    assert editor.outlineView.outline_context is editor.outline_context
    assert editor.settings is settings
    assert window.projectRuntime.models.outline.settings is settings
    assert item.settings is settings
    assert (
        editor.txtRedacText.text_editor_context
        is window.workspaceProject.text_editor_context
    )
    assert (
        window.mainEditor.tabSplitter.editor_context
        is window.mainEditor.editor_context
    )
    assert (
        window.mainEditor.tabSplitter.settings
        is settings
    )
    assert window.mainEditor.tabSplitter.tabOpenIndexes() == [item.ID()]

    window.mainEditor.tabSplitter.split(state=1)
    assert (
        window.mainEditor.tabSplitter.secondTab.editor_context
        is window.mainEditor.editor_context
    )

    window.mainEditor.closeAllTabs()


def test_full_screen_asks_the_mode_and_hands_it_the_editor_context(
        MWEmptyProject):
    """The button carries no knowledge of modes, only of what it is showing.

    What it must still do is describe the pane completely, so whichever
    presentation answers has everything it needs without reaching back.
    """
    window = MWEmptyProject
    item = outlineItem(title="Chapter", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()
    asked = []

    class Recording:
        def enter(self, request):
            asked.append(request)
            return None

    with patch.object(
        main_editor_module,
        "QDesktopWidget",
    ) as desktop, patch.object(
        main_editor_module,
        "fullscreen_presentation_for",
        lambda mode: Recording(),
    ):
        desktop.return_value.screenNumber.return_value = 0

        window.mainEditor.showFullScreen()

    request, = asked
    assert request.index == index
    assert request.widget is editor
    assert request.settings is window.projectRuntime.settingsManager
    assert request.text_editor_context is (
        window.workspaceProject.text_editor_context
    )
    assert request.markup_profile is editor.markupProfile
    assert request.screen_number == 0


def test_full_screen_routes_through_the_mode_on_screen(MWEmptyProject):
    """A mode is asked for itself, not for whatever the button assumed."""
    window = MWEmptyProject
    item = outlineItem(title="Chapter", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()
    asked = []

    with patch.object(
        main_editor_module,
        "QDesktopWidget",
    ) as desktop, patch.object(
        main_editor_module,
        "fullscreen_presentation_for",
        lambda mode: asked.append(mode) or _declining(),
    ):
        desktop.return_value.screenNumber.return_value = 0

        window.mainEditor.showFullScreen()

    assert asked == [editor.markdownPresentation.mode]
    window.mainEditor.closeAllTabs()


def test_active_editor_selection_sync_refreshes_main_editor(
        MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor()

    with patch.object(window.mainEditor, "tabChanged") as tab_changed:
        editor._syncActiveEditorSelection()

    tab_changed.assert_called_once_with()
    window.mainEditor.closeAllTabs()


def test_markdown_modes_are_visible_and_synchronized(MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Chapter")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    manuscript_editor = window.mainEditor.currentEditor().txtRedacText
    # The one-sentence summary is deliberately a plain line edit.  Use the
    # full-summary Markdown editor to prove that presentation changes remain
    # scoped to the active manuscript editor.
    summary_editor = window.corePanels.metadata.txtSummaryFull
    selector = window.mainEditor.cmbMarkdownMode
    state = window.mainEditor.currentEditor().markdownPresentation

    assert (
        window.menuMarkdownMode.menuAction()
        in window.menuView.actions()
    )
    assert selector.isEnabled()
    assert selector.currentText() == "Formatted Source"

    selector.setCurrentIndex(0)

    assert state.mode is MarkdownPresentationMode.SOURCE
    assert window.markdownMenu.actions[
        MarkdownPresentationMode.SOURCE
    ].isChecked()

    window.markdownMenu.actions[
        MarkdownPresentationMode.FORMATTED_SOURCE
    ].trigger()

    assert state.mode is MarkdownPresentationMode.FORMATTED_SOURCE
    assert selector.currentText() == "Formatted Source"

    window.markdownMenu.actions[
        MarkdownPresentationMode.CLEAN_EDITING
    ].trigger()

    assert state.mode is MarkdownPresentationMode.CLEAN_EDITING
    assert selector.currentText() == "Clean Editing"

    window.markdownMenu.actions[
        MarkdownPresentationMode.READING
    ].trigger()

    assert state.mode is MarkdownPresentationMode.READING
    assert selector.currentText() == "Reading"
    assert (
        manuscript_editor.presentationMode
        is MarkdownPresentationMode.READING
    )
    assert (
        summary_editor.presentationMode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert summary_editor.readingView is None
    window.mainEditor.closeAllTabs()


def test_max_width_centers_the_shared_markdown_host(MWEmptyProject):
    window = MWEmptyProject
    window_was_visible = window.isVisible()
    settings = window.projectRuntime.settingsManager
    old_max_width = settings.textEditor["maxWidth"]
    old_background = settings.textEditor["background"]
    old_transparency = settings.textEditor[
        "backgroundTransparent"
    ]
    settings.textEditor["maxWidth"] = 600
    settings.textEditor["background"] = "#f7f4ee"
    settings.textEditor["backgroundTransparent"] = False
    window.resize(1400, 720)
    window.show()
    item = outlineItem(title="Centered page", _type="md")
    item.setData(
        Outline.text,
        "A paragraph long enough to make the editor geometry visible.",
    )
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    try:
        window.mainEditor.setCurrentModelIndex(index, newTab=True)
        editor = window.mainEditor.currentEditor()
        editor.txtRedacText.loadFontSettings()
        qApp.processEvents()

        host = editor.markdownEditorHost
        available_width = editor.text.contentsRect().width()
        expected_left = (available_width - host.width()) // 2

        assert host.maximumWidth() == 600
        assert host.width() == min(600, available_width)
        assert abs(host.x() - expected_left) <= 1
        assert editor.txtRedacText.width() == host.contentsRect().width()
        assert "background: #f7f4ee" in editor.text.styleSheet()

        editor.markdownPresentation.set_mode(
            MarkdownPresentationMode.READING
        )
        qApp.processEvents()

        assert host.currentWidget() is editor.txtRedacText.readingView
        assert editor.txtRedacText.readingView.width() == (
            host.contentsRect().width()
        )
    finally:
        window.mainEditor.closeAllTabs()
        settings.textEditor["maxWidth"] = old_max_width
        settings.textEditor["background"] = old_background
        settings.textEditor[
            "backgroundTransparent"
        ] = old_transparency
        if not window_was_visible:
            window.hide()


def test_workspace_width_override_preserves_editor_preference(MWEmptyProject):
    window = MWEmptyProject
    settings = window.projectRuntime.settingsManager
    old_max_width = settings.textEditor["maxWidth"]
    settings.textEditor["maxWidth"] = 640
    item = outlineItem(title="Comparable page", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    try:
        window.mainEditor.setCurrentModelIndex(index, newTab=True)
        host = window.mainEditor.currentEditor().markdownEditorHost
        host.sourceEditor.loadFontSettings()

        host.setMaximumWidthOverride(480)
        assert host.maximumWidth() == 480
        assert host.effectiveMaximumWidth == 480

        host.clearMaximumWidthOverride()
        assert host.maximumWidth() == 640
        assert host.effectiveMaximumWidth == 640
    finally:
        window.mainEditor.closeAllTabs()
        settings.textEditor["maxWidth"] = old_max_width


def test_markdown_mode_is_owned_by_each_editor_tab(MWEmptyProject):
    window = MWEmptyProject
    first_item = outlineItem(title="First")
    second_item = outlineItem(title="Second")
    window.projectRuntime.models.outline.appendItem(first_item)
    window.projectRuntime.models.outline.appendItem(second_item)
    first_index = window.projectRuntime.models.outline.indexFromItem(first_item)
    second_index = window.projectRuntime.models.outline.indexFromItem(second_item)

    window.mainEditor.setCurrentModelIndex(first_index, newTab=True)
    first_editor = window.mainEditor.currentEditor()
    window.markdownMenu.actions[
        MarkdownPresentationMode.LIVE_PREVIEW
    ].trigger()

    window.mainEditor.setCurrentModelIndex(second_index, newTab=True)
    second_editor = window.mainEditor.currentEditor()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    assert (
        window.mainEditor.cmbMarkdownMode.currentText()
        == "Formatted Source"
    )

    first_editor._tabWidget.setCurrentWidget(first_editor)

    assert (
        window.mainEditor.cmbMarkdownMode.currentText()
        == "Live Preview"
    )
    assert window.markdownMenu.actions[
        MarkdownPresentationMode.LIVE_PREVIEW
    ].isChecked()
    # The button walks the modes this leaf allows, in their order, so what it
    # offers next is whatever follows the current one rather than a mode it
    # was built to prefer.
    assert (
        first_editor.markdownModeButton.toolTip()
        == "Switch to Clean Editing"
    )

    first_editor.markdownModeButton.click()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.CLEAN_EDITING
    )
    assert (
        first_editor.markdownModeButton.toolTip()
        == "Switch to Reading"
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )
    window.mainEditor.closeAllTabs()


def test_markdown_mode_is_independent_between_split_leaves(
        MWEmptyProject):
    window = MWEmptyProject
    window_was_visible = window.isVisible()
    window.resize(1100, 720)
    window.show()
    item = outlineItem(title="Chapter", _type="md")
    item.setData(
        Outline.text,
        "# Chapter 1\n\n"
        "**Bunker, Kyiv. June. Daytime.**\n\n"
        "First paragraph with *rendered emphasis*.\n\n"
        "Second paragraph stays independent.",
    )
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    first_editor = window.mainEditor.currentEditor()
    first_editor.markdownPresentation.set_mode(
        MarkdownPresentationMode.LIVE_PREVIEW
    )

    window.mainEditor.tabSplitter.split(state=1)
    second_editor = window.mainEditor.currentEditor()

    assert second_editor is not first_editor
    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.FORMATTED_SOURCE
    )

    second_editor.markdownPresentation.set_mode(
        MarkdownPresentationMode.READING
    )
    qApp.processEvents()

    assert (
        first_editor.markdownPresentation.mode
        is MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert (
        second_editor.markdownPresentation.mode
        is MarkdownPresentationMode.READING
    )
    assert (
        first_editor.markdownEditorHost.currentWidget()
        is first_editor.txtRedacText
    )
    assert first_editor.txtRedacText.isVisible()
    assert (
        second_editor.markdownEditorHost.currentWidget()
        is second_editor.txtRedacText.readingView
    )
    assert second_editor.txtRedacText.isHidden()
    window.mainEditor.closeAllTabs()
    if not window_was_visible:
        window.hide()


def test_mode_button_always_renders_an_icon(MWEmptyProject):
    """The icon is the whole control: a null one is an invisible target."""
    window = MWEmptyProject
    item = outlineItem(window.projectRuntime.models.outline, title="Iconned", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    window.mainEditor.setCurrentModelIndex(
        window.projectRuntime.models.outline.indexFromItem(item), newTab=True
    )
    editor = window.mainEditor.currentEditor()

    try:
        for mode in MarkdownPresentationMode:
            if mode not in editor.markdownPresentation.allowed_modes:
                continue
            editor.markdownPresentation.set_mode(mode)
            qApp.processEvents()
            assert not editor.markdownModeButton.icon().isNull(), mode
            assert editor.markdownModeButton.toolTip()
        assert not editor.markupProfileButton.icon().isNull()
    finally:
        window.mainEditor.closeAllTabs()


def test_overlay_buttons_do_not_sit_on_top_of_the_text(MWEmptyProject):
    """Reserved strip keeps the first line clear of the floating buttons."""
    window = MWEmptyProject
    item = outlineItem(window.projectRuntime.models.outline, title="Spaced", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    window.mainEditor.setCurrentModelIndex(
        window.projectRuntime.models.outline.indexFromItem(item), newTab=True
    )
    editor = window.mainEditor.currentEditor()

    def reserved_top():
        # Read the margin itself: layouts do not activate while the test
        # window is unrealized, so mapped geometry would lag behind.
        return editor.verticalLayout_2.getContentsMargins()[1]

    try:
        qApp.processEvents()
        button = editor.markdownModeButton
        assert button.isVisibleTo(editor)
        needed = button.y() + button.height()

        # Reading and the page wizard are sibling views swapped into the
        # same stack, so the strip has to survive every mode, not just the
        # source editor the buttons were first measured against.
        for mode in MarkdownPresentationMode:
            if mode not in editor.markdownPresentation.allowed_modes:
                continue
            editor.markdownPresentation.set_mode(mode)
            qApp.processEvents()
            assert reserved_top() >= needed, mode

        # A view without the buttons must not keep the empty strip.
        editor.stack.setCurrentIndex(3)
        editor._updateMarkdownModeButtonVisibility()

        assert reserved_top() == 0
    finally:
        window.mainEditor.closeAllTabs()
