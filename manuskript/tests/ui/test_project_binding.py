import ast
import inspect
from unittest.mock import MagicMock

import pytest

from manuskript.ui.project_binding import ProjectBinding
from manuskript.ui import (
    project_binding,
    project_feature_binding,
    project_view_binding,
)


def window_names(module):
    """Names that would let a binding grow a MainWindow dependency."""
    tree = ast.parse(inspect.getsource(module))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "window" in node.id.lower():
            found.add(node.id)
        elif isinstance(node, ast.arg) and "window" in node.arg.lower():
            found.add(node.arg)
        elif (
            isinstance(node, ast.Attribute)
            and "window" in node.attr.lower()
        ):
            found.add(node.attr)
    return found


def test_project_bindings_cannot_reach_through_a_main_window():
    """Only ProjectBindingViews may translate a window into contracts."""
    for module in (
        project_binding,
        project_feature_binding,
        project_view_binding,
    ):
        assert window_names(module) == set(), module.__name__


def make_binding():
    # The context binding is built at bind time, from the factory, since
    # there are no models to bind until a project is open. A test says
    # what that factory hands back rather than assigning afterwards.
    contexts = MagicMock()
    views = MagicMock()
    views.surface_instances.return_value = ()
    features = MagicMock()
    binding = ProjectBinding(
        views,
        MagicMock(),
        features,
        contexts_factory=lambda: contexts,
    )
    binding.flat_data = MagicMock()
    binding.features = features
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


def test_project_binding_attaches_and_detaches_living_surfaces():
    binding = make_binding()
    first = MagicMock(id="core.general")
    binding.surfaceInstances = MagicMock(return_value=(first,))

    binding.bind()

    binding.flat_data.attach_surface.assert_called_once_with(first)
    binding.contexts.attach_surface.assert_called_once_with(first)
    binding.outline_selection.attach_surface.assert_called_once_with(first)

    second = MagicMock(id="core.editor")
    binding.attach_surface(second)
    binding.detach_surface(second)

    binding.outline_selection.detach_surface.assert_any_call(second)
    binding.contexts.detach_surface.assert_any_call(second)
    binding.flat_data.detach_surface.assert_any_call(second)
