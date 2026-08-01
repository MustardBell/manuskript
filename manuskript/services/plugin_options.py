import json

from manuskript.plugins.api import normalize_options


class PluginOptionStore:
    """Persist JSON-compatible extension options by stable extension ID."""

    PREFIX = "plugins/options/"

    def __init__(self, settings):
        self._settings = settings

    def load(self, extension_id, fields=()):
        return normalize_options(
            fields,
            self.load_values(extension_id),
        )

    def load_values(self, extension_id):
        value = self._settings.value(self.PREFIX + extension_id)
        if value is None:
            decoded = {}
        else:
            try:
                decoded = json.loads(str(value))
            except (TypeError, ValueError):
                decoded = {}
        if not isinstance(decoded, dict):
            decoded = {}
        return decoded

    def save(self, extension_id, values):
        self._settings.setValue(
            self.PREFIX + extension_id,
            json.dumps(
                dict(values),
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        self._settings.sync()


class InMemoryPluginOptionStore:
    def __init__(self):
        self.values = {}

    def load(self, extension_id, fields=()):
        return normalize_options(
            fields,
            self.load_values(extension_id),
        )

    def load_values(self, extension_id):
        return dict(self.values.get(extension_id, {}))

    def save(self, extension_id, values):
        self.values[extension_id] = dict(values)
