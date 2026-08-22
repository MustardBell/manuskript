"""What the installed plugins contribute, for the whole application.

The plugin runtime owns loading; the windows own menus and panels. What
was missing between them was anywhere for one fact to live: *the set of
contributions changed*.

Without it, that fact was announced by whichever window's plugin manager
happened to be open, to itself. Enabling a plugin from one window left
every other window's menus, page types, markup profiles and card styles
as they were -- silently, since nothing failed. Two windows made a
question of what one window could leave implicit.

So enabling and disabling happen here, and here is what tells everyone.
A caller cannot change the set and forget to say so, because saying so
is not a separate step it could omit.
"""

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.media_types import core_registry
from manuskript.plugins.contracts import (
    ContributionKind,
    ContributionScope,
)


class PluginContributionService(QObject):
    """Application scope: what plugins offer, and when that changes."""

    #: The set of contributions is no longer what it was. Every window
    #: refreshes its own view of it; nobody refreshes anybody else's.
    changed = pyqtSignal()

    def __init__(
            self, runtime, option_store=None, media_types=None,
            parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.optionStore = option_store
        self.mediaTypes = (
            media_types if media_types is not None else core_registry()
        )

    # ------------------------------------------- what plugins contribute

    @property
    def registry(self):
        return self.runtime.registry

    @property
    def records(self):
        return self.runtime.records

    @property
    def discovery_issues(self):
        return self.runtime.discovery_issues

    def plugin_records(self, plugin_id, kind):
        return self.registry.plugin_records(plugin_id, kind)

    def scope_granted(
            self, plugin_id, kind, contribution_id,
            scope=ContributionScope.ALL):
        return self.runtime.preferences.scope_granted(
            plugin_id, kind, contribution_id, scope
        )

    # -------------------------------------------------- changing the set

    def enable(self, plugin_id):
        record = self.runtime.enable(plugin_id)
        self.announce()
        return record

    def disable(self, plugin_id):
        record = self.runtime.disable(plugin_id)
        self.announce()
        return record

    def rediscover(self):
        """Look again at what is installed, and load what is enabled."""
        records = self.runtime.discover()
        self.runtime.load_enabled()
        self.announce()
        return records

    def set_project_format(self, version):
        """Activate only contributions valid for the current project."""
        records = self.runtime.set_project_format(version)
        self.announce()
        return records

    def set_scope_grant(
            self, plugin_id, kind, contribution_id, scope, granted):
        """Set reader authority only for a declaration that requests it."""

        kind = ContributionKind(kind)
        scope = ContributionScope(scope)
        matching = tuple(
            record
            for record in self.registry.plugin_records(plugin_id, kind)
            if record.id == contribution_id
        )
        if not matching:
            raise ValueError(
                "Plugin {} has no {} contribution {!r}.".format(
                    plugin_id, kind.value, contribution_id,
                )
            )
        requested = getattr(
            matching[0].contribution,
            "scope",
            ContributionScope.OWN,
        )
        if scope is not ContributionScope.ALL or requested is not scope:
            raise ValueError(
                "Contribution {!r} did not request {} reach.".format(
                    contribution_id, scope.value,
                )
            )
        self.runtime.preferences.set_scope_grant(
            plugin_id, kind, contribution_id, scope, bool(granted)
        )
        self.announce()

    def announce(self):
        """Say the set changed.

        Public because a plugin may be enabled by something other than
        this service -- at startup, say -- and whoever does that owes
        everyone the same notice.
        """
        self.changed.emit()
