import json

from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)


def create_plugin(
        root,
        plugin_id="example.plugin",
        api_version=1,
        source=None):
    plugin_root = root / plugin_id
    plugin_root.mkdir()
    (plugin_root / "plugin.json").write_text(
        json.dumps({
            "id": plugin_id,
            "name": "Test plugin",
            "version": "1.0",
            "api_version": api_version,
            "entry_point": "plugin:register",
        }),
        encoding="utf-8",
    )
    (plugin_root / "plugin.py").write_text(
        source or (
            "from manuskript.plugins import ("
            "ExportContribution, ExtensionDescriptor)\n"
            "def register(api):\n"
            "    api.register_exporter(ExportContribution(\n"
            "        descriptor=ExtensionDescriptor(\n"
            "            id='example.export', name='Example'),\n"
            "        engine_factory=object,\n"
            "    ))\n"
        ),
        encoding="utf-8",
    )
    return plugin_root


def test_disabled_plugins_are_discovered_without_executing_code(tmp_path):
    plugin_root = create_plugin(
        tmp_path,
        source=(
            "raise RuntimeError('disabled plugin was executed')\n"
        ),
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(),
    )

    records = runtime.discover()

    assert len(records) == 1
    assert records[0].status is PluginStatus.DISABLED
    assert runtime.registry.exporters == ()
    assert plugin_root.exists()


def test_enabling_plugin_loads_contributions_immediately(tmp_path):
    create_plugin(tmp_path)
    preferences = InMemoryPluginPreferences()
    runtime = PluginRuntime([tmp_path], preferences)
    runtime.discover()

    record = runtime.enable("example.plugin")

    assert record.status is PluginStatus.LOADED
    assert preferences.enabled_plugin_ids == ("example.plugin",)
    assert [
        value.descriptor.id
        for value in runtime.registry.exporters
    ] == ["example.export"]

    runtime.disable("example.plugin")

    assert runtime.registry.exporters == ()
    assert preferences.enabled_plugin_ids == ()


def test_incompatible_plugin_is_never_imported(tmp_path):
    create_plugin(
        tmp_path,
        api_version=999,
        source="raise RuntimeError('must not execute')\n",
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["example.plugin"]
    assert record.status is PluginStatus.INCOMPATIBLE
    assert "requires API 999" in record.error


def test_failed_registration_leaves_no_partial_contributions(tmp_path):
    create_plugin(
        tmp_path,
        source=(
            "from manuskript.plugins import ("
            "ExportContribution, ExtensionDescriptor)\n"
            "def contribution():\n"
            "    return ExportContribution(\n"
            "        ExtensionDescriptor('duplicate', 'Duplicate'),"
            " object)\n"
            "def register(api):\n"
            "    api.register_exporter(contribution())\n"
            "    api.register_exporter(contribution())\n"
        ),
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    assert (
        runtime.records["example.plugin"].status
        is PluginStatus.FAILED
    )
    assert runtime.registry.exporters == ()


def test_plugin_package_supports_relative_imports(tmp_path):
    plugin_root = create_plugin(
        tmp_path,
        source=(
            "from .identity import extension_name\n"
            "from manuskript.plugins import ("
            "ExportContribution, ExtensionDescriptor)\n"
            "def register(api):\n"
            "    api.register_exporter(ExportContribution(\n"
            "        ExtensionDescriptor('relative', extension_name),"
            " object))\n"
        ),
    )
    (plugin_root / "identity.py").write_text(
        "extension_name = 'Relative import'\n",
        encoding="utf-8",
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    assert (
        runtime.registry.exporters[0].descriptor.name
        == "Relative import"
    )
