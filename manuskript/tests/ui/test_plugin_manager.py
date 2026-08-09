import json

from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)
from manuskript.services.plugin_contributions import (
    PluginContributionService,
)
from manuskript.tests.plugins.test_runtime import create_plugin
from manuskript.ui.plugins.manager import PluginManagerDialog


def contributions(runtime):
    """What the dialog changes the plugin set through.

    Enabling goes through the service so that every window hears about
    it, not only the one the dialog was opened from.
    """
    return PluginContributionService(runtime)


def test_manager_discovers_disabled_plugin_without_loading_it(tmp_path):
    create_plugin(tmp_path)
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(),
    )

    dialog = PluginManagerDialog(contributions(runtime))

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
    service = contributions(runtime)
    dialog = PluginManagerDialog(service)
    monkeypatch.setattr(
        dialog,
        "_confirm_enable",
        lambda _plugin_id: True,
    )
    # The announcement belongs to the service, not to this dialog: every
    # window subscribes to it, so a change made here reaches all of them.
    changes = []
    service.changed.connect(lambda: changes.append(True))

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

    dialog = PluginManagerDialog(contributions(runtime))

    assert "Discovery problems" in dialog.discoveryLabel.text()
    assert "Invalid plugin ID" in dialog.discoveryLabel.text()
