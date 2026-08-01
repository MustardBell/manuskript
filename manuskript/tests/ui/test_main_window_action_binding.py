import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.commands import DocumentCommand
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
    ), patch.object(binding_module, "qApp", MagicMock()):
        binding = MainWindowActionBinding(window)
        binding.bind()

    window.projectManager.syncUiToState.assert_called_once_with()
    window.actOpen.triggered.connect.assert_called_once_with(
        window.welcome.openFile
    )
    window.actSave.triggered.connect.assert_called_once_with(
        window.projectManager.saveDatas
    )
    window.actBack.triggered.connect.assert_called_once_with(
        window.navigationController.back
    )
    window.generateViewMenu.assert_called_once_with()
    (
        window.mainEditor.activeMarkdownPresentationStateChanged.connect
        .assert_called_once_with(window.attachMarkdownPresentationState)
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
    live_preview_slot = (
        window.actMarkdownLivePreview.triggered.connect.call_args.args[0]
    )
    live_preview_slot()
    window.setMarkdownPresentationMode.assert_called_once_with(
        MarkdownPresentationMode.LIVE_PREVIEW
    )
    assert binding.bound


def test_main_window_action_binding_installs_permanent_feature_signals():
    window = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=MagicMock(),
    ), patch.object(binding_module, "qApp", MagicMock()) as application:
        MainWindowActionBinding(window).bind()

    window.txtPersosFilter.textChanged.connect.assert_called_once()
    window.lstPlots.currentItemChanged.connect.assert_called_once()
    window.btnRedacAddFolder.clicked.connect.assert_called_once()
    window.tabMain.currentChanged.connect.assert_any_call(
        window.toolbar.setCurrentGroup
    )
    application.focusChanged.connect.assert_called_once_with(
        window.focusChanged
    )


def test_main_window_action_binding_rejects_duplicate_install():
    window = MagicMock()

    with patch.object(
        binding_module,
        "QActionGroup",
        return_value=MagicMock(),
    ), patch.object(binding_module, "qApp", MagicMock()):
        binding = MainWindowActionBinding(window)
        binding.bind()
        with pytest.raises(RuntimeError, match="only be bound once"):
            binding.bind()
