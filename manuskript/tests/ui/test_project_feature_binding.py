import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.ui.project_feature_binding import ProjectFeatureBinding

binding_module = importlib.import_module(
    "manuskript.ui.project_feature_binding"
)


def make_controllers():
    """Controllers expose only their models and typed panel contracts."""
    characters = MagicMock()
    plots = MagicMock()
    world = MagicMock()
    characters.models = MagicMock()
    plots.models = MagicMock()
    world.models = MagicMock()
    characters.panel.fields = tuple(MagicMock() for _ in range(10))
    plots.panel.fields = tuple(MagicMock() for _ in range(4))
    world.panel.fields = tuple(MagicMock() for _ in range(4))
    world.models.world.columnCount.return_value = 2
    return characters, plots, world


def make_binding():
    controllers = make_controllers()
    settings = MagicMock()
    return (
        ProjectFeatureBinding(*controllers, settings),
        controllers,
        settings,
    )


def test_project_feature_binding_installs_all_feature_models():
    binding, controllers, settings = make_binding()
    characters, plots, world = controllers
    connect = MagicMock()

    with patch.object(
        binding_module,
        "outlineCharacterDelegate",
        side_effect=lambda model, _parent: MagicMock(
            mdlCharacter=model,
        ),
    ), patch.object(
        binding_module,
        "plotDelegate",
        return_value=MagicMock(),
    ):
        binding.bind(connect)

    characters.panel.characters.setCharactersModel.assert_called_once_with(
        characters.models.characters
    )
    plots.panel.plots.setPlotModel.assert_called_once_with(
        plots.models.plots,
        settings=settings,
    )
    world.panel.tree.setModel.assert_called_once_with(world.models.world)
    assert binding.bound
    assert connect.call_count >= 10


def test_feature_bindings_resolve_replaced_models_on_every_bind():
    """A binding must not retain the model set of the previous project."""
    binding, controllers, _settings = make_binding()
    characters, plots, world = controllers
    first = characters.models.characters

    with patch.object(
        binding_module,
        "outlineCharacterDelegate",
        side_effect=lambda model, _parent: MagicMock(
            mdlCharacter=model,
        ),
    ), patch.object(
        binding_module,
        "plotDelegate",
        return_value=MagicMock(),
    ):
        binding.bind(MagicMock())
        binding.unbind()
        replacement = MagicMock()
        characters.models.characters = replacement
        plots.models.characters = replacement
        binding.bind(MagicMock())

    assert (
        characters.panel.characters.setCharactersModel.call_args_list[0]
        .args[0]
    ) is first
    assert (
        characters.panel.characters.setCharactersModel.call_args_list[1]
        .args[0]
    ) is replacement
    assert binding.bindings[1]._character_delegate.mdlCharacter is (
        replacement
    )
    # Keep the composite reusable for its real owner.
    binding.unbind()


def test_project_feature_binding_resets_features_in_reverse_lifecycle():
    binding, _controllers, _settings = make_binding()
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
    binding, _controllers, _settings = make_binding()
    for feature in binding.bindings:
        feature.bind = MagicMock()

    binding.bind(MagicMock())

    with pytest.raises(RuntimeError, match="released"):
        binding.bind(MagicMock())


def test_project_feature_binding_rolls_back_partial_install():
    binding, _controllers, _settings = make_binding()
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
