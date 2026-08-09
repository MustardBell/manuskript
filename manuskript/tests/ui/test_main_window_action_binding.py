import importlib
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtGui import QTextCursor

from manuskript.commands import DocumentCommand, MarkupCommand
from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.main_window_action_binding import (
    MainWindowActionBinding,
)

binding_module = importlib.import_module(
    "manuskript.ui.main_window_action_binding"
)


def test_main_window_action_binding_routes_lifecycle_and_commands():
    window = MagicMock()
    action_group = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=action_group,
    ):
        binding = MainWindowActionBinding(window)
        binding.bind()

    window.projectManager.syncUiToState.assert_called_once_with()
    window.actOpen.triggered.connect.assert_called_once()
    window.actSave.triggered.connect.assert_called_once()
    window.actGitRevisions.triggered.connect.assert_called_once()
    window.actImport.triggered.connect.assert_called_once()
    window.actCompile.triggered.connect.assert_called_once()
    window.actQuit.triggered.connect.assert_called_once()
    window.actBack.triggered.connect.assert_called_once()
    window.actSettings.triggered.connect.assert_called_once()
    window.actToolTargets.triggered.connect.assert_called_once()
    window.viewSettingsMenu.rebuild.assert_called_once_with()
    (
        window.mainEditor.activeMarkdownPresentationStateChanged.connect
        .assert_called_once()
    )
    window.actModeSimple.setActionGroup.assert_called_once_with(
        action_group
    )
    window.actMarkdownLivePreview.setActionGroup.assert_called_once_with(
        action_group
    )
    window.actMarkdownFormattedSource.setActionGroup.assert_called_once_with(
        action_group
    )

    copy_slot = window.actCopy.triggered.connect.call_args.args[0]
    copy_slot()
    window.documentCommands.dispatch.assert_called_once_with(
        DocumentCommand.COPY
    )
    bold_slot = window.actFormatBold.triggered.connect.call_args.args[0]
    bold_slot()
    window.markupCommands.dispatch.assert_called_once_with(
        MarkupCommand.BOLD
    )
    search_slot = window.actSearch.triggered.connect.call_args.args[0]
    search_slot()
    window.workspaceSearch.show.assert_called_once_with()
    simple_mode_slot = (
        window.actModeSimple.triggered.connect.call_args.args[0]
    )
    simple_mode_slot()
    window.viewConfigurationController.set_simple.assert_called_once_with()
    live_preview_slot = (
        window.actMarkdownLivePreview.triggered.connect.call_args.args[0]
    )
    live_preview_slot()
    window.markdownMenu.set_mode.assert_called_once_with(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert binding.bound
    assert not hasattr(binding, "window")
    assert binding._window is None


def test_main_window_action_binding_installs_permanent_feature_signals():
    window = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=MagicMock(),
    ):
        MainWindowActionBinding(window).bind()

    window.txtPersosFilter.textChanged.connect.assert_called_once()
    window.lstPlots.currentItemChanged.connect.assert_called_once()
    (
        window.corePanels.project_tree.add_folder.clicked.connect
        .assert_called_once()
    )
    assert window.tabMain.currentChanged.connect.call_count == 2
    toolbar_slot = (
        window.tabMain.currentChanged.connect.call_args_list[0].args[0]
    )
    toolbar_slot(3)
    window.toolbar.setCurrentGroup.assert_called_once_with(3)
    # Focus is application-wide, so the window registry watches it once
    # for the application and forwards to whichever workspace gained it.
    # Connecting here, per window, had every window react to every other
    # window's focus changes.
    window.windowRegistry.watch_focus.assert_called_once_with()


def test_main_window_action_binding_rejects_duplicate_install():
    window = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=MagicMock(),
    ):
        binding = MainWindowActionBinding(window)
        binding.bind()
        with pytest.raises(RuntimeError, match="only be bound once"):
            binding.bind()


def test_main_window_action_binding_releases_owned_connections():
    window = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=MagicMock(),
    ):
        binding = MainWindowActionBinding(window)
        binding.bind()

    assert len(binding._connections) > 0

    binding.dispose()

    assert len(binding._connections) == 0
    quit_slot = window.actQuit.triggered.connect.call_args.args[0]
    new_window_slot = (
        window.actNewWindow.triggered.connect.call_args.args[0]
    )
    window.actQuit.triggered.disconnect.assert_called_once_with(quit_slot)
    window.actNewWindow.triggered.disconnect.assert_called_once_with(
        new_window_slot
    )


def test_format_action_reaches_the_active_markup_editor(MWEmptyProject):
    window = MWEmptyProject
    item = outlineItem(title="Command routing", _type="md")
    item.setData(Outline.text, "select me")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.mainEditor.setCurrentModelIndex(index, newTab=True)
    editor = window.mainEditor.currentEditor().txtRedacText
    try:
        cursor = editor.textCursor()
        cursor.select(QTextCursor.Document)
        editor.setTextCursor(cursor)
        window.workspaceFocus.focus_changed(None, editor)

        window.actFormatBold.trigger()

        assert editor.toPlainText() == "**select me**"
    finally:
        window.mainEditor.closeAllTabs()
