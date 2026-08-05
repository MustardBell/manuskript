import hashlib
import importlib
import logging
import sys
import types
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from manuskript.plugins.api import PLUGIN_API_VERSION
from manuskript.plugins.capabilities import grant
from manuskript.plugins.errors import (
    PluginCompatibilityError,
    PluginLoadError,
    PluginManifestError,
    PluginRegistrationError,
)
from manuskript.media_types import (
    PROMISES,
    MediaTypeError,
    core_registry,
)
from manuskript.plugins.manifest import PluginManifest
from manuskript.plugins.registry import (
    PluginRegistry,
    contribution_media_types,
)


LOGGER = logging.getLogger(__name__)


class PluginStatus(str, Enum):
    DISABLED = "disabled"
    LOADED = "loaded"
    INCOMPATIBLE = "incompatible"
    #: Sound plugin, but it asked for a service core does not provide.
    UNSATISFIED = "unsatisfied"
    FAILED = "failed"


@dataclass
class PluginRecord:
    manifest: PluginManifest
    status: PluginStatus
    loadable: bool = True
    error: str = ""
    handle: object = None
    module_prefix: str = ""


@dataclass(frozen=True)
class PluginDiscoveryIssue:
    path: str
    error: str


class PluginRuntime:
    """Discover manifests safely and execute only explicitly enabled plugins."""

    def __init__(
        self,
        roots,
        preferences,
        registry=None,
        api_version=PLUGIN_API_VERSION,
        media_types=None,
    ):
        self.roots = tuple(Path(root).resolve() for root in roots)
        self.preferences = preferences
        self.registry = registry or PluginRegistry()
        self.api_version = api_version
        self.mediaTypes = (
            media_types if media_types is not None else core_registry()
        )
        self.records = {}
        self.discovery_issues = []

    def discover(self):
        enabled = set(self.preferences.enabled_plugin_ids)
        previous_records = self.records
        discovered = {}
        issues = []

        for root in self.roots:
            if not root.exists():
                continue
            for manifest_file in sorted(root.glob("*/plugin.json")):
                try:
                    manifest = PluginManifest.load(manifest_file)
                except PluginManifestError as error:
                    issues.append(
                        PluginDiscoveryIssue(
                            str(manifest_file),
                            str(error),
                        )
                    )
                    continue

                previous = discovered.get(manifest.id)
                if previous is not None:
                    message = (
                        "Duplicate plugin ID {} in {} and {}."
                    ).format(
                        manifest.id,
                        previous.manifest.root,
                        manifest.root,
                    )
                    issues.append(
                        PluginDiscoveryIssue(
                            str(manifest.root),
                            message,
                        )
                    )
                    discovered[manifest.id] = PluginRecord(
                        manifest=previous.manifest,
                        status=PluginStatus.FAILED,
                        loadable=False,
                        error=message,
                    )
                    continue

                existing = previous_records.get(manifest.id)
                if (
                    existing is not None
                    and existing.status is PluginStatus.LOADED
                    and existing.manifest == manifest
                ):
                    discovered[manifest.id] = existing
                else:
                    discovered[manifest.id] = PluginRecord(
                        manifest=manifest,
                        status=(
                            PluginStatus.DISABLED
                            if manifest.id not in enabled
                            else PluginStatus.FAILED
                        ),
                        error=(
                            ""
                            if manifest.id not in enabled
                            else "Enabled plugin has not been loaded."
                        ),
                    )

        for plugin_id, previous in previous_records.items():
            if discovered.get(plugin_id) is not previous:
                self._deactivate_record(previous)

        self.records = discovered
        self.discovery_issues = issues
        self._declare_media_types(discovered.values())
        return tuple(self.records.values())

    def _declare_media_types(self, records):
        """Put every discovered plugin's vocabulary into the registry.

        Declaring happens at discovery, not at load, and for disabled
        plugins too. Load order is arbitrary, so a format registered while
        running would exist or not depending on which plugin came first;
        read from the manifest it is there for everyone. It also means the
        inspector can show who has an interest in a format without anyone's
        code having run.
        """
        for record in records:
            manifest = record.manifest
            for media_type in manifest.media_types:
                try:
                    self.mediaTypes.declare(media_type, manifest.id)
                except MediaTypeError as error:
                    LOGGER.warning(
                        "Plugin %s declared media type %s that cannot be "
                        "used: %s",
                        manifest.id,
                        media_type.id,
                        error,
                    )
            for kind in PROMISES:
                for name in getattr(manifest, kind, ()):
                    try:
                        self.mediaTypes.promise(name, kind, manifest.id)
                    except MediaTypeError as error:
                        LOGGER.warning(
                            "Plugin %s promise about %s ignored: %s",
                            manifest.id,
                            name,
                            error,
                        )

    def load_enabled(self):
        if not self.records:
            self.discover()
        enabled = set(self.preferences.enabled_plugin_ids)
        for plugin_id, record in sorted(self.records.items()):
            if plugin_id in enabled:
                self.load(plugin_id)
        return tuple(self.records.values())

    def enable(self, plugin_id):
        self._record(plugin_id)
        self.preferences.enable(plugin_id)
        return self.load(plugin_id)

    def disable(self, plugin_id):
        record = self._record(plugin_id)
        self.preferences.disable(plugin_id)
        self._deactivate_record(record)
        record.status = PluginStatus.DISABLED
        record.error = ""
        return record

    def load(self, plugin_id):
        record = self._record(plugin_id)
        manifest = record.manifest
        if record.status is PluginStatus.LOADED:
            return record
        if not record.loadable:
            return record

        if manifest.api_version != self.api_version:
            error = PluginCompatibilityError(
                "Plugin {} requires API {}, but Manuskript provides API {}."
                .format(
                    manifest.id,
                    manifest.api_version,
                    self.api_version,
                )
            )
            record.status = PluginStatus.INCOMPATIBLE
            record.error = str(error)
            return record

        # Negotiate before anything of the plugin's runs. A plugin whose
        # requirements core cannot meet is refused, not half-started.
        capabilities, missing = grant(manifest.requires)
        if missing:
            record.status = PluginStatus.UNSATISFIED
            record.error = (
                "Plugin {} requires {} which this Manuskript does not "
                "provide.".format(
                    manifest.id,
                    ", ".join(missing),
                )
            )
            return record

        registrar = self.registry.registrar(
            plugin_id,
            capabilities=capabilities,
        )
        module_prefix = self._module_prefix(manifest)
        try:
            entry = self._load_entry_point(
                manifest,
                module_prefix,
            )
            handle = entry(registrar)
            self._require_promised(manifest, registrar.contributions)
            self.registry.install(
                plugin_id,
                registrar.contributions,
            )
        except Exception as error:
            self.registry.remove_plugin(plugin_id)
            self._remove_modules(module_prefix)
            failure = PluginLoadError(
                "Cannot load plugin {}: {}: {}".format(
                    plugin_id,
                    type(error).__name__,
                    error,
                )
            )
            record.status = PluginStatus.FAILED
            record.error = str(failure)
            LOGGER.exception("%s", failure)
            return record

        record.handle = handle
        record.module_prefix = module_prefix
        record.status = PluginStatus.LOADED
        record.error = ""
        return record

    @staticmethod
    def _require_promised(manifest, contributions):
        """Contributions may only work with formats the manifest promised.

        The manifest says what a plugin does with a format; the code has to
        agree. Registration is atomic, so one contribution naming an
        unpromised format installs none of them rather than leaving the
        plugin half-present.
        """
        promised = set(manifest.promised_media_types)
        for record in contributions:
            named = contribution_media_types(
                record.kind,
                record.contribution,
            )
            unpromised = sorted(named - promised)
            if unpromised:
                raise PluginRegistrationError(
                    "{} {} works with {}, which plugin {} did not promise "
                    "to produce, consume or transform.".format(
                        record.kind.value,
                        record.id,
                        ", ".join(unpromised),
                        manifest.id,
                    )
                )

    def _load_entry_point(self, manifest, module_prefix):
        package = types.ModuleType(module_prefix)
        package.__path__ = [str(manifest.root)]
        package.__package__ = module_prefix
        sys.modules[module_prefix] = package
        module_name = "{}.{}".format(
            module_prefix,
            manifest.entry_module,
        )
        try:
            module = importlib.import_module(module_name)
        except Exception:
            self._remove_modules(module_prefix)
            raise
        entry = getattr(module, manifest.entry_callable, None)
        if not callable(entry):
            raise PluginLoadError(
                "Entry point {}:{} is not callable.".format(
                    manifest.entry_module,
                    manifest.entry_callable,
                )
            )
        return entry

    def _record(self, plugin_id):
        if plugin_id not in self.records:
            raise KeyError("Unknown plugin {!r}.".format(plugin_id))
        return self.records[plugin_id]

    def _deactivate_record(self, record):
        plugin_id = record.manifest.id
        self.registry.remove_plugin(plugin_id)
        handle = record.handle
        if handle is not None and hasattr(handle, "deactivate"):
            try:
                handle.deactivate()
            except Exception:
                LOGGER.exception(
                    "Plugin %s failed while deactivating.",
                    plugin_id,
                )
        self._remove_modules(record.module_prefix)
        record.handle = None
        record.module_prefix = ""

    @staticmethod
    def _module_prefix(manifest):
        digest = hashlib.sha256(
            str(manifest.root).encode("utf-8")
        ).hexdigest()[:16]
        return "_manuskript_plugin_{}".format(digest)

    @staticmethod
    def _remove_modules(prefix):
        if not prefix:
            return
        for module_name in [
            name
            for name in sys.modules
            if name == prefix or name.startswith(prefix + ".")
        ]:
            sys.modules.pop(module_name, None)
