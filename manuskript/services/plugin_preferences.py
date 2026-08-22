from manuskript.plugins.contracts import (
    ContributionKind,
    ContributionScope,
)


class PluginPreferences:
    """Persist enabled plugins and reader-authorized contribution reach."""

    ENABLED_KEY = "plugins/enabled"
    SCOPE_GRANTS_KEY = "plugins/scopeGrants"

    def __init__(self, settings):
        self._settings = settings

    @property
    def enabled_plugin_ids(self):
        value = self._settings.value(
            self.ENABLED_KEY,
            [],
        )
        if value is None:
            return ()
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

    def scope_granted(
            self, plugin_id, kind, contribution_id,
            scope=ContributionScope.ALL):
        return self._scope_token(
            plugin_id, kind, contribution_id, scope
        ) in self._scope_grants

    def set_scope_grant(
            self, plugin_id, kind, contribution_id, scope, granted):
        token = self._scope_token(
            plugin_id, kind, contribution_id, scope
        )
        grants = set(self._scope_grants)
        if granted:
            grants.add(token)
        else:
            grants.discard(token)
        self._settings.setValue(self.SCOPE_GRANTS_KEY, sorted(grants))
        self._settings.sync()

    @property
    def _scope_grants(self):
        value = self._settings.value(self.SCOPE_GRANTS_KEY, [])
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        return tuple(dict.fromkeys(str(item) for item in value))

    @staticmethod
    def _scope_token(plugin_id, kind, contribution_id, scope):
        kind = ContributionKind(kind)
        scope = ContributionScope(scope)
        return "{}|{}|{}|{}".format(
            str(plugin_id), kind.value, str(contribution_id), scope.value,
        )

    def _write(self, plugin_ids):
        self._settings.setValue(
            self.ENABLED_KEY,
            list(plugin_ids),
        )
        self._settings.sync()


class InMemoryPluginPreferences:
    def __init__(self, enabled=(), scope_grants=()):
        self._enabled = list(enabled)
        self._grants = set(scope_grants)

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

    def scope_granted(
            self, plugin_id, kind, contribution_id,
            scope=ContributionScope.ALL):
        return PluginPreferences._scope_token(
            plugin_id, kind, contribution_id, scope
        ) in self._grants

    def set_scope_grant(
            self, plugin_id, kind, contribution_id, scope, granted):
        token = PluginPreferences._scope_token(
            plugin_id, kind, contribution_id, scope
        )
        if granted:
            self._grants.add(token)
        else:
            self._grants.discard(token)
