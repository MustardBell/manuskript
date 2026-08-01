import json

from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)
from manuskript.tests.plugins.test_runtime import create_plugin
from manuskript.ui.plugins.manager import PluginManagerDialog


def test_manager_discovers_disabled_plugin_without_loading_it(tmp_path):
    create_plugin(tmp_path)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(),
    )

    dialog = PluginManagerDialog(runtime)

    assert dialog.pluginList.topLevelItemCount() == 1
    assert (
        runtime.records["example.plugin"].status
        is PluginStatus.DISABLED
    )
    assert runtime.registry.exporters == ()


def test_manager_enables_and_disables_selected_plugin(
        tmp_path, monkeypatch):
    create_plugin(tmp_path)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(),
    )
    dialog = PluginManagerDialog(runtime)
    monkeypatch.setattr(
        dialog,
        "_confirm_enable",
        lambda _plugin_id: True,
    )
    changes = []
    dialog.pluginsChanged.connect(lambda: changes.append(True))

    dialog.enable_selected()

    assert (
        runtime.records["example.plugin"].status
        is PluginStatus.LOADED
    )
    assert len(runtime.registry.exporters) == 1

    dialog.disable_selected()

    assert (
        runtime.records["example.plugin"].status
        is PluginStatus.DISABLED
    )
    assert runtime.registry.exporters == ()
    assert changes == [True, True]


def test_manager_reports_invalid_manifests(tmp_path):
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "plugin.json").write_text(
        json.dumps({
            "id": "../escape",
            "name": "Broken",
            "version": "1.0",
            "api_version": 1,
            "entry_point": "plugin:register",
        }),
        encoding="utf-8",
    )
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(),
    )

    dialog = PluginManagerDialog(runtime)

    assert "Discovery problems" in dialog.discoveryLabel.text()
    assert "Invalid plugin ID" in dialog.discoveryLabel.text()
