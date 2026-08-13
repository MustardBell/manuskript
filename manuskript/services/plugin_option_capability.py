"""Plugin-scoped portable access to host-persisted extension options."""

from manuskript.plugins.api import PluginOptionsSnapshot
from manuskript.plugins.errors import PluginScopeError


class PluginOptionsCapability:
    def __init__(self, plugin_id, registry, store):
        self.pluginId = str(plugin_id)
        self.registry = registry
        self.store = store

    def read(self, extension_id):
        extension_id = self._owned(extension_id)
        return PluginOptionsSnapshot(
            extension_id,
            self.store.load_values(extension_id),
        )

    def write(self, extension_id, values):
        extension_id = self._owned(extension_id)
        if not isinstance(values, dict) or not all(
            isinstance(key, str) for key in values
        ):
            raise TypeError("Plugin option values must be a string-keyed map.")
        self.store.save(extension_id, values)
        return self.read(extension_id)

    def _owned(self, extension_id):
        extension_id = str(extension_id)
        owned = {
            record.id for record in self.registry.plugin_records(self.pluginId)
        }
        if extension_id not in owned:
            raise PluginScopeError(
                "Plugin {} does not own extension {!r}."
                .format(self.pluginId, extension_id)
            )
        return extension_id
