import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.ui.project_feature_binding import ProjectFeatureBinding

binding_module = importlib.import_module(
    "manuskript.ui.project_feature_binding"
)


def make_window():
    return MagicMock()


def make_runtime():
    """The project the widgets show, separate from the window showing it."""
    runtime = MagicMock()
    runtime.models.world.columnCount.return_value = 2
    return runtime


def test_project_feature_binding_installs_all_feature_models():
    window = make_window()
    runtime = make_runtime()
    connect = MagicMock()

    with patch.object(
        binding_module,
        "outlineCharacterDelegate",
        return_value=MagicMock(),
    ), patch.object(
        binding_module,
        "plotDelegate",
        return_value=MagicMock(),
    ):
        binding = ProjectFeatureBinding(window, runtime)
        binding.bind(connect)

    window.lstCharacters.setCharactersModel.assert_called_once_with(
        runtime.models.characters
    )
    window.lstPlots.setPlotModel.assert_called_once_with(
        runtime.models.plots,
        settings=window.settingsManager,
    )
    window.treeWorld.setModel.assert_called_once_with(runtime.models.world)
    assert binding.bound
    assert connect.call_count >= 10


def test_project_feature_binding_resets_features_in_reverse_lifecycle():
    window = make_window()
    runtime = make_runtime()
    binding = ProjectFeatureBinding(window, runtime)
    for feature in binding.bindings:
        feature.bind = MagicMock()
        feature.unbind = MagicMock()

    binding.bind(MagicMock())
    binding.unbind()

    for feature in binding.bindings:
        feature.bind.assert_called_once()
        feature.unbind.assert_called_once_with()
    assert not binding.bound


def test_project_feature_binding_rejects_double_binding():
    window = make_window()
    runtime = make_runtime()
    binding = ProjectFeatureBinding(window, runtime)
    for feature in binding.bindings:
        feature.bind = MagicMock()

    binding.bind(MagicMock())

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())


def test_project_feature_binding_rolls_back_partial_install():
    window = make_window()
    runtime = make_runtime()
    binding = ProjectFeatureBinding(window, runtime)
    first, second, third = binding.bindings
    for feature in binding.bindings:
        feature.bind = MagicMock()
        feature.unbind = MagicMock()
    second.bind.side_effect = RuntimeError("broken feature")

    with pytest.raises(RuntimeError, match="broken feature"):
        binding.bind(MagicMock())

    first.unbind.assert_called_once_with()
    second.unbind.assert_not_called()
    third.bind.assert_not_called()
    assert not binding.bound
