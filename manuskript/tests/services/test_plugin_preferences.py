from manuskript.services.plugin_preferences import PluginPreferences


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
