class PluginPreferences:
    """Persist the explicit set of trusted/enabled Python plugins."""

    ENABLED_KEY = "plugins/enabled"

    def __init__(self, settings):
        self._settings = settings

    @property
    def enabled_plugin_ids(self):
        value = self._settings.value(
            self.ENABLED_KEY,
            [],
        )
        if isinstance(value, str):
            value = [value]
        return tuple(dict.fromkeys(str(item) for item in value))

    def enable(self, plugin_id):
        enabled = list(self.enabled_plugin_ids)
        if plugin_id not in enabled:
            enabled.append(plugin_id)
            self._write(enabled)

    def disable(self, plugin_id):
        self._write(
            item
            for item in self.enabled_plugin_ids
            if item != plugin_id
        )

    def _write(self, plugin_ids):
        self._settings.setValue(
            self.ENABLED_KEY,
            list(plugin_ids),
        )
        self._settings.sync()


class InMemoryPluginPreferences:
    def __init__(self, enabled=()):
        self._enabled = list(enabled)

    @property
    def enabled_plugin_ids(self):
        return tuple(self._enabled)

    def enable(self, plugin_id):
        if plugin_id not in self._enabled:
            self._enabled.append(plugin_id)

    def disable(self, plugin_id):
        self._enabled = [
            value for value in self._enabled
            if value != plugin_id
        ]
