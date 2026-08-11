from unittest.mock import MagicMock

import pytest

from manuskript.ui.project_feature_binding import ProjectFeatureBinding


def test_project_feature_binding_owns_the_entity_workspace_lifecycle():
    workspace = MagicMock()
    binding = ProjectFeatureBinding(workspace)
    connect = MagicMock()

    binding.bind(connect)
    binding.unbind()

    workspace.bind.assert_called_once_with(connect)
    workspace.unbind.assert_called_once_with()
    assert not binding.bound


def test_project_feature_binding_rejects_double_binding():
    binding = ProjectFeatureBinding(MagicMock())
    binding.bind(MagicMock())

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())


def test_project_feature_binding_disposes_the_entity_workspace():
    workspace = MagicMock()
    binding = ProjectFeatureBinding(workspace)
    binding.bind(MagicMock())

    binding.dispose()

    workspace.unbind.assert_called_once_with()
    workspace.dispose.assert_called_once_with()
    assert binding.entityWorkspace is None
