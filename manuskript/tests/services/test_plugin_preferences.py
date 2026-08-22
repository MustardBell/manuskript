from manuskript.services.plugin_preferences import PluginPreferences
from manuskript.plugins.contracts import ContributionKind, ContributionScope


class SettingsStub:
    def __init__(self, value):
        self.stored_value = value

    def value(self, _key, _default):
        return self.stored_value


def test_enabled_plugin_ids_normalizes_qsettings_null_value():
    preferences = PluginPreferences(SettingsStub(None))

    assert preferences.enabled_plugin_ids == ()


def test_enabled_plugin_ids_normalizes_single_qsettings_string():
    preferences = PluginPreferences(SettingsStub("example.plugin"))

    assert preferences.enabled_plugin_ids == ("example.plugin",)


class WritableSettingsStub:
    def __init__(self):
        self.values = {}
        self.sync_count = 0

    def value(self, key, default):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value

    def sync(self):
        self.sync_count += 1


def test_scope_grants_are_explicit_persisted_and_revocable():
    settings = WritableSettingsStub()
    preferences = PluginPreferences(settings)
    arguments = (
        "example.graph",
        ContributionKind.PRESENTATION_MODE,
        "example.graph.mode",
        ContributionScope.ALL,
    )

    assert not preferences.scope_granted(*arguments)

    preferences.set_scope_grant(*arguments, True)

    assert preferences.scope_granted(*arguments)
    assert settings.values[PluginPreferences.SCOPE_GRANTS_KEY] == [
        "example.graph|presentation_mode|example.graph.mode|all"
    ]

    preferences.set_scope_grant(*arguments, False)

    assert not preferences.scope_granted(*arguments)
    assert settings.values[PluginPreferences.SCOPE_GRANTS_KEY] == []
    assert settings.sync_count == 2
