import pytest

from manuskript.plugins.api import (
    CommandContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.plugin_option_capability import (
    PluginOptionsCapability,
)
from manuskript.services.plugin_options import InMemoryPluginOptionStore


def capability():
    registry = PluginRegistry()
    registrar = registry.registrar("example.options")
    registrar.register_command(CommandContribution(
        ExtensionDescriptor("example.options.command", "Run"),
        lambda: None,
    ))
    registry.install("example.options", registrar.contributions)
    return PluginOptionsCapability(
        "example.options", registry, InMemoryPluginOptionStore()
    )


def test_options_are_host_persisted_for_an_owned_extension():
    service = capability()

    assert service.read("example.options.command").values == {}
    saved = service.write(
        "example.options.command", {"language": "uk", "limit": 12}
    )

    assert saved.values == {"language": "uk", "limit": 12}
    assert service.read("example.options.command") == saved


def test_plugin_cannot_read_or_write_another_extension_namespace():
    service = capability()

    with pytest.raises(PluginScopeError, match="does not own"):
        service.read("other.plugin.command")
    with pytest.raises(PluginScopeError, match="does not own"):
        service.write("other.plugin.command", {"stolen": True})
