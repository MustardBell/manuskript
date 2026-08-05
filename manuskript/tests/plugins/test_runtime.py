import json

from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)


def create_plugin(
        root,
        plugin_id="example.plugin",
        api_version=1,
        source=None,
        manifest=None):
    plugin_root = root / plugin_id
    plugin_root.mkdir()
    declared = {
        "id": plugin_id,
        "name": "Test plugin",
        "version": "1.0",
        "api_version": api_version,
        "entry_point": "plugin:register",
    }
    declared.update(manifest or {})
    (plugin_root / "plugin.json").write_text(
        json.dumps(declared),
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


FAILING_INSTALL_SOURCE = (
    # The entry point succeeds and returns a handle, then install refuses
    # the plugin: the transform names a media type the manifest never
    # promised. That failure happens after plugin code already ran.
    "from pathlib import Path\n"
    "from manuskript.plugins import ("
    "ExtensionDescriptor, TransformContribution)\n"
    "class Handle:\n"
    "    def deactivate(self):\n"
    "        Path(__file__).with_name('deactivated').touch()\n"
    "{extra}"
    "def register(api):\n"
    "    api.register_transform(TransformContribution(\n"
    "        ExtensionDescriptor('example.transform', 'Example'),\n"
    "        media_type='text/x-unpromised',\n"
    "        engine_factory=object,\n"
    "    ))\n"
    "    return Handle()\n"
)


def test_install_failure_deactivates_what_the_entry_point_started(
        tmp_path):
    """The entry point may have connected signals or started timers by the
    time install refuses the plugin, so its handle must get the same
    deactivate call an unload would give it.
    """
    create_plugin(tmp_path, source=FAILING_INSTALL_SOURCE.format(extra=""))
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["example.plugin"]
    assert record.status is PluginStatus.FAILED
    assert "text/x-unpromised" in record.error
    assert (tmp_path / "example.plugin" / "deactivated").exists()
    assert runtime.registry.transforms == ()


def test_a_failing_deactivate_never_masks_the_install_error(tmp_path):
    """Cleanup is a courtesy to the plugin; the reported failure stays the
    one that refused it.
    """
    create_plugin(
        tmp_path,
        source=FAILING_INSTALL_SOURCE.format(
            extra=(
                "class BrokenHandle:\n"
                "    def deactivate(self):\n"
                "        raise RuntimeError('cleanup exploded')\n"
            ),
        ).replace("return Handle()", "return BrokenHandle()"),
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["example.plugin"]
    assert record.status is PluginStatus.FAILED
    assert "text/x-unpromised" in record.error
    assert "cleanup exploded" not in record.error


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


def test_refresh_unloads_a_plugin_removed_from_disk(tmp_path):
    plugin_root = create_plugin(tmp_path)
    preferences = InMemoryPluginPreferences(["example.plugin"])
    runtime = PluginRuntime([tmp_path], preferences)
    runtime.discover()
    runtime.load_enabled()
    (plugin_root / "plugin.json").unlink()

    runtime.discover()

    assert runtime.records == {}
    assert runtime.registry.exporters == ()


def test_refresh_unloads_plugin_when_manifest_becomes_duplicate(tmp_path):
    create_plugin(tmp_path)
    preferences = InMemoryPluginPreferences(["example.plugin"])
    runtime = PluginRuntime([tmp_path], preferences)
    runtime.discover()
    runtime.load_enabled()
    duplicate_root = tmp_path / "duplicate"
    duplicate_root.mkdir()
    (duplicate_root / "plugin.json").write_text(
        json.dumps({
            "id": "example.plugin",
            "name": "Duplicate",
            "version": "1.0",
            "api_version": 1,
            "entry_point": "plugin:register",
        }),
        encoding="utf-8",
    )

    runtime.discover()

    assert (
        runtime.records["example.plugin"].status
        is PluginStatus.FAILED
    )
    assert runtime.registry.exporters == ()


def test_preinstalled_plugin_uses_normal_enable_disable_state(tmp_path):
    create_plugin(tmp_path, plugin_id="preinstalled.plugin")
    preferences = InMemoryPluginPreferences()
    runtime = PluginRuntime([tmp_path], preferences)

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["preinstalled.plugin"]
    assert record.status is PluginStatus.DISABLED
    assert preferences.enabled_plugin_ids == ()

    runtime.enable("preinstalled.plugin")

    assert record.status is PluginStatus.LOADED
    assert len(runtime.registry.exporters) == 1

    runtime.disable("preinstalled.plugin")

    assert record.status is PluginStatus.DISABLED
    assert runtime.registry.exporters == ()
    assert preferences.enabled_plugin_ids == ()


def test_duplicate_plugin_ids_across_roots_are_rejected(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    create_plugin(first, plugin_id="duplicate.plugin")
    create_plugin(second, plugin_id="duplicate.plugin")
    runtime = PluginRuntime(
        [first, second],
        InMemoryPluginPreferences(["duplicate.plugin"]),
    )

    runtime.discover()
    runtime.load_enabled()

    record = runtime.records["duplicate.plugin"]
    assert record.manifest.root.parent == first
    assert record.status is PluginStatus.FAILED
    assert runtime.registry.exporters == ()
    assert "Duplicate plugin ID" in runtime.discovery_issues[0].error
