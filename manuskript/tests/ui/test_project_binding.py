from unittest.mock import MagicMock

import pytest

from manuskript.ui.project_binding import ProjectBinding


def make_binding():
    # The context binding is built at bind time, from the factory, since
    # there are no models to bind until a project is open. A test says
    # what that factory hands back rather than assigning afterwards.
    contexts = MagicMock()
    binding = ProjectBinding(
        MagicMock(),
        MagicMock(),
        contexts_factory=lambda: contexts,
    )
    binding.flat_data = MagicMock()
    binding.features = MagicMock()
    binding.outline_selection = MagicMock()
    binding.debug_views = MagicMock()
    binding.expectedContexts = contexts
    return binding


def test_project_binding_owns_complete_binding_lifecycle():
    binding = make_binding()
    reference_service = MagicMock()
    text_editor_context = MagicMock()
    contexts = binding.expectedContexts
    contexts.reference_service = reference_service
    contexts.text_editor_context = text_editor_context

    # Before binding there is no context binding at all, and asking is
    # answered rather than raising.
    assert binding.reference_service is None
    assert binding.text_editor_context is None

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
    binding.expectedContexts.bind.side_effect = RuntimeError(
        "broken context"
    )
    binding.connections.disconnect_all = MagicMock()

    with pytest.raises(RuntimeError, match="broken context"):
        binding.bind()

    binding.connections.disconnect_all.assert_called_once_with()
    binding.contexts.unbind.assert_called_once_with()
    binding.features.unbind.assert_called_once_with()
    binding.outline_selection.bind.assert_not_called()
    assert not binding.bound
