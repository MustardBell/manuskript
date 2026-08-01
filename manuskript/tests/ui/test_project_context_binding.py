import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.views.MDEditCompleter import MDEditCompleter
from manuskript.ui.views.textEditView import textEditView

binding_module = importlib.import_module(
    "manuskript.ui.project_context_binding"
)


def make_window():
    window = MagicMock()
    text_editor = MagicMock()
    completer = MagicMock()

    def find_children(widget_type):
        if widget_type is textEditView:
            return [text_editor]
        if widget_type is MDEditCompleter:
            return [completer]
        return []

    window.findChildren.side_effect = find_children
    return window, text_editor, completer


def test_project_context_binding_installs_and_releases_contexts():
    window, text_editor, completer = make_window()
    reference_service = MagicMock()
    text_context = MagicMock()
    outline_context = MagicMock()
    editor_context = MagicMock()
    search_context = MagicMock()
    connect = MagicMock()

    with patch.object(
        binding_module,
        "ReferenceService",
        return_value=reference_service,
    ), patch.object(
        binding_module,
        "text_editor_context_for",
        return_value=text_context,
    ), patch.object(
        binding_module,
        "OutlineViewContext",
        return_value=outline_context,
    ), patch.object(
        binding_module,
        "EditorContext",
        return_value=editor_context,
    ), patch.object(
        binding_module.SearchContext,
        "from_models",
        return_value=search_context,
    ):
        binding = ProjectContextBinding(window)
        binding.bind(connect)

    assert binding.reference_service is reference_service
    assert binding.text_editor_context is text_context
    text_editor.set_text_editor_context.assert_called_once_with(
        text_context
    )
    window.mainEditor.set_context.assert_called_once_with(
        editor_context
    )
    completer.setReferenceService.assert_called_once()
    window.widget.setContext.assert_called_once_with(search_context)

    binding.unbind()

    text_editor.set_text_editor_context.assert_called_with(None)
    completer.setReferenceService.assert_called_with(None)
    window.mainEditor.clear_context.assert_called_once_with()
    window.widget.clearContext.assert_called_once_with()
    assert binding.reference_service is None
    assert binding.text_editor_context is None


def test_project_context_binding_rejects_double_binding():
    window, _text_editor, _completer = make_window()
    binding = ProjectContextBinding(window)
    binding.reference_service = MagicMock()

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())
