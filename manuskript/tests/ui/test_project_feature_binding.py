import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.ui.project_feature_binding import ProjectFeatureBinding

binding_module = importlib.import_module(
    "manuskript.ui.project_feature_binding"
)


def make_window():
    window = MagicMock()
    window.mdlWorld.columnCount.return_value = 2
    return window


def test_project_feature_binding_installs_all_feature_models():
    window = make_window()
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
        binding = ProjectFeatureBinding(window)
        binding.bind(connect)

    window.lstCharacters.setCharactersModel.assert_called_once_with(
        window.mdlCharacter
    )
    window.lstPlots.setPlotModel.assert_called_once_with(
        window.mdlPlots,
        settings=window.settingsManager,
    )
    window.treeWorld.setModel.assert_called_once_with(window.mdlWorld)
    assert binding.bound
    assert connect.call_count >= 10


def test_project_feature_binding_resets_features_in_reverse_lifecycle():
    window = make_window()
    binding = ProjectFeatureBinding(window)
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
    binding = ProjectFeatureBinding(window)
    for feature in binding.bindings:
        feature.bind = MagicMock()

    binding.bind(MagicMock())

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())
