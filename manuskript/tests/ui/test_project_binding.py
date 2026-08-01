from unittest.mock import MagicMock

import pytest

from manuskript.ui.project_binding import ProjectBinding


def make_binding():
    binding = ProjectBinding(MagicMock())
    binding.flat_data = MagicMock()
    binding.features = MagicMock()
    binding.contexts = MagicMock()
    binding.outline_selection = MagicMock()
    binding.debug_views = MagicMock()
    return binding


def test_project_binding_owns_complete_binding_lifecycle():
    binding = make_binding()
    reference_service = MagicMock()
    text_editor_context = MagicMock()
    binding.contexts.reference_service = reference_service
    binding.contexts.text_editor_context = text_editor_context

    binding.bind()

    binding.flat_data.bind.assert_called_once_with(
        binding.connections.connect
    )
    binding.features.bind.assert_called_once_with(
        binding.connections.connect
    )
    binding.contexts.bind.assert_called_once_with(
        binding.connections.connect
    )
    binding.outline_selection.bind.assert_called_once_with(
        binding.connections.connect
    )
    binding.debug_views.bind.assert_called_once_with(
        binding.connections.connect
    )
    assert binding.reference_service is reference_service
    assert binding.text_editor_context is text_editor_context
    assert binding.bound

    binding.unbind()

    binding.contexts.unbind.assert_called_once_with()
    binding.features.unbind.assert_called_once_with()
    assert not binding.bound


def test_project_binding_rejects_double_binding():
    binding = make_binding()
    binding.bind()

    with pytest.raises(RuntimeError, match="released"):
        binding.bind()


def test_project_binding_rolls_back_a_failed_context_install():
    binding = make_binding()
    binding.contexts.bind.side_effect = RuntimeError("broken context")
    binding.connections.disconnect_all = MagicMock()

    with pytest.raises(RuntimeError, match="broken context"):
        binding.bind()

    binding.connections.disconnect_all.assert_called_once_with()
    binding.contexts.unbind.assert_called_once_with()
    binding.features.unbind.assert_called_once_with()
    binding.outline_selection.bind.assert_not_called()
    assert not binding.bound
