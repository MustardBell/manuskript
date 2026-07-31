import pytest

from manuskript.plugins.api import (
    ExportContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.registry import PluginRegistry


def exporter(extension_id):
    return ExportContribution(
        descriptor=ExtensionDescriptor(
            id=extension_id,
            name=extension_id,
        ),
        engine_factory=object,
    )


def test_registry_installs_one_plugin_atomically():
    registry = PluginRegistry()
    registrar = registry.registrar("example.first")
    registrar.register_exporter(exporter("example.fb2"))

    registry.install(
        "example.first",
        registrar.contributions,
    )

    assert registry.exporters == (
        registrar.contributions[0].contribution,
    )


def test_registry_rejects_cross_plugin_ids_without_partial_install():
    registry = PluginRegistry()
    first = registry.registrar("example.first")
    first.register_exporter(exporter("example.fb2"))
    registry.install("example.first", first.contributions)
    second = registry.registrar("example.second")
    second.register_exporter(exporter("example.mobi"))
    second.register_exporter(exporter("example.fb2"))

    with pytest.raises(
        PluginRegistrationError,
        match="already registered",
    ):
        registry.install("example.second", second.contributions)

    assert [
        contribution.descriptor.id
        for contribution in registry.exporters
    ] == ["example.fb2"]
