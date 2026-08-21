import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from manuskript.plugins.api import PLUGIN_API_VERSION
from manuskript.plugins.capabilities import (
    PluginCapabilityContext,
    grant,
)
from manuskript.plugins.errors import (
    PluginCompatibilityError,
    PluginLoadError,
    PluginManifestError,
    PluginRegistrationError,
    PluginScopeError,
)
from manuskript.media_types import (
    PROMISES,
    MediaTypeError,
    core_registry,
)
from manuskript.plugins.manifest import PluginManifest
from manuskript.plugins.drivers import (
    PluginDriverContext,
    ProcessPluginDriver,
    PythonPluginDriver,
)
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
    warning: str = ""
    driver: object = None
    session: object = None


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
        project_format=None,
        application_capability_resolver=None,
        project_capability_resolver=None,
        drivers=None,
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
        self.projectFormat = project_format
        self.projectGeneration = 0
        #: Who may hold which capability. Deliberately owned here, at the
        #: plugin-runtime boundary, rather than decided privately inside
        #: whatever builds a capability -- a builder that also invents
        #: authorization policy is a second policy nobody can see. None
        #: until the composition root installs one, and a capability built
        #: without it simply carries no grant.
        self.capabilityAuthority = None
        self._applicationCapabilityResolver = application_capability_resolver
        self._projectCapabilityResolver = project_capability_resolver
        drivers = tuple(
            (PythonPluginDriver(), ProcessPluginDriver())
            if drivers is None else drivers
        )
        kinds = [driver.kind for driver in drivers]
        if len(kinds) != len(set(kinds)):
            raise ValueError("Plugin driver kinds must be unique.")
        self.drivers = {driver.kind: driver for driver in drivers}

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
                        warning=self._project_format_warning(manifest),
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
        # Authority is taken in _deactivate_record, which every path that
        # ends a loaded incarnation goes through. Retiring here as well
        # would advance the epoch twice for one event.
        self._deactivate_record(record)
        record.status = PluginStatus.DISABLED
        record.error = ""
        record.warning = self._project_format_warning(record.manifest)
        return record

    def load(self, plugin_id):
        record = self._record(plugin_id)
        manifest = record.manifest
        if record.status is PluginStatus.LOADED:
            return record
        if not record.loadable:
            return record

        if (
            self.projectFormat is not None
            and not manifest.supports_project_format(self.projectFormat)
        ):
            record.status = PluginStatus.INCOMPATIBLE
            record.error = self._project_format_error(manifest)
            record.warning = ""
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
            record.warning = ""
            return record

        driver = self.drivers.get(manifest.runtime.kind)
        if driver is None:
            record.status = PluginStatus.UNSATISFIED
            record.error = (
                "Plugin {} uses the {} runtime, which this development "
                "build cannot execute yet."
            ).format(plugin_id, manifest.runtime.kind.value)
            record.warning = ""
            return record
        availability = driver.availability(manifest)
        if not availability.available:
            record.status = PluginStatus.UNSATISFIED
            record.error = availability.error
            record.warning = ""
            return record

        # Negotiate before anything of the plugin's runs. A plugin whose
        # requirements core cannot meet is refused, not half-started.
        required_capabilities = driver.required_capabilities(manifest)
        optional_capability_names = driver.optional_capabilities(manifest)
        capabilities, missing = grant(
            required_capabilities, self.capabilityContext()
        )
        if missing:
            record.status = PluginStatus.UNSATISFIED
            record.error = (
                "Plugin {} requires {} which this Manuskript does not "
                "provide.".format(
                    manifest.id,
                    ", ".join(missing),
                )
            )
            record.warning = ""
            return record

        unavailable_optional = []
        for name in optional_capability_names:
            optional_capabilities, unavailable = grant(
                (name,), self.capabilityContext()
            )
            capabilities.update(optional_capabilities)
            unavailable_optional.extend(unavailable)

        registrar = self.registry.registrar(
            plugin_id,
            capabilities=capabilities,
            declared_capabilities=(
                manifest.requires + manifest.optional
            ),
            unavailable_capabilities=tuple(unavailable_optional),
        )
        session = None
        try:
            session = driver.load(
                manifest,
                registrar,
                PluginDriverContext(
                    api_version=self.api_version,
                    project_format=self.projectFormat,
                    project_generation=self.projectGeneration,
                    generation_source=lambda: self.projectGeneration,
                    capability_resolver=lambda name: (
                        self._resolve_process_capability(
                            plugin_id, registrar, name
                        )
                    ),
                ),
            )
            self._require_promised(manifest, registrar.contributions)
            self.registry.install(
                plugin_id,
                registrar.contributions,
            )
            driver.activate(manifest, session, registrar)
        except Exception as error:
            # The entry point already ran and may have connected signals or
            # started timers. Whatever it started has to be told to stop,
            # and while its modules are still importable.
            driver.deactivate(manifest, session)
            self.registry.remove_plugin(plugin_id)
            failure = PluginLoadError(
                "Cannot load plugin {}: {}: {}".format(
                    plugin_id,
                    type(error).__name__,
                    error,
                )
            )
            record.status = PluginStatus.FAILED
            record.error = str(failure)
            record.warning = ""
            LOGGER.exception("%s", failure)
            return record

        record.driver = driver
        record.session = session
        record.status = PluginStatus.LOADED
        record.error = ""
        record.warning = self._project_format_warning(manifest)
        return record

    def set_project_format(self, version):
        """Make enabled plugins match the project before its UI connects."""

        version = None if version is None else int(version)
        if version == self.projectFormat:
            return tuple(self.records.values())
        self.projectFormat = version
        self.projectGeneration += 1
        enabled = set(self.preferences.enabled_plugin_ids)
        for plugin_id, record in sorted(self.records.items()):
            record.warning = self._project_format_warning(record.manifest)
            if plugin_id not in enabled or not record.loadable:
                continue
            compatible = (
                version is None
                or record.manifest.supports_project_format(version)
            )
            if not compatible:
                if record.status is PluginStatus.LOADED:
                    self._deactivate_record(record)
                record.status = PluginStatus.INCOMPATIBLE
                record.error = self._project_format_error(record.manifest)
                record.warning = ""
                continue
            if record.status is not PluginStatus.LOADED:
                self.load(plugin_id)
            elif compatible:
                record.warning = self._project_format_warning(
                    record.manifest
                )
                record.driver.project_changed(
                    record.manifest,
                    record.session,
                    self.projectGeneration,
                    self.projectFormat,
                )
        return tuple(self.records.values())

    def set_capability_authority(self, authority):
        """Install the one owner of who may hold which capability."""

        self.capabilityAuthority = authority

    def set_project_capability_resolver(self, resolver):
        """Install the composition-root bridge to current project services."""

        if resolver is not None and not callable(resolver):
            raise TypeError("Project capability resolver must be callable.")
        self._projectCapabilityResolver = resolver

    def set_application_capability_resolver(self, resolver):
        """Install scoped services that do not require an open project."""

        if resolver is not None and not callable(resolver):
            raise TypeError("Application capability resolver must be callable.")
        self._applicationCapabilityResolver = resolver

    def publish_project_event(self, topic, payload):
        """Send an ordered event only to live subscribed process plugins."""

        for record in tuple(self.records.values()):
            if record.status is not PluginStatus.LOADED:
                continue
            record.driver.publish_event(
                record.manifest,
                record.session,
                topic,
                payload,
            )

    def _resolve_process_capability(self, plugin_id, registrar, name):
        try:
            return registrar.capability(name)
        except PluginScopeError as local_error:
            if self._applicationCapabilityResolver is not None:
                try:
                    return self._applicationCapabilityResolver(plugin_id, name)
                except PluginScopeError:
                    pass
            if self._projectCapabilityResolver is not None:
                return self._projectCapabilityResolver(plugin_id, name)
            raise local_error

    def _project_format_error(self, manifest):
        return (
            "Plugin {} supports project formats {}, but the open project "
            "uses format {}."
        ).format(
            manifest.id,
            manifest.project_formats.label,
            self.projectFormat,
        )

    def _project_format_warning(self, manifest):
        if (
            self.projectFormat is None
            or not manifest.project_formats.is_tentative(
                self.projectFormat
            )
        ):
            return ""
        return (
            "Plugin {} has only been explicitly tested through project "
            "format {}; format {} is tentatively allowed."
        ).format(
            manifest.id,
            manifest.project_formats.tested_through,
            self.projectFormat,
        )

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
                record.declaration,
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

    def capabilityContext(self):
        """What a capability may be built from, beyond nothing.

        A service that has to see what other plugins contributed cannot come
        from a plain factory, and reaching a runtime through a global to get
        it would be the service locator this codebase has been removing. So
        the runtime hands over what it has, and the catalogue says which
        capabilities want it.

        The registry is passed live rather than as a snapshot: a plugin
        enabled later contributes to conversions performed later, which is
        what enabling a plugin is expected to mean.
        """
        # Imported here, not at module scope: the conversion service reads
        # the plugin API, which is this package, so importing it from here
        # makes the two modules import each other. Whichever is imported
        # first then decides whether either works at all.
        from manuskript.converters.conversion_service import (
            conversion_service,
        )

        return PluginCapabilityContext(
            registry=self.registry,
            conversion_service=lambda: conversion_service(
                registry=self.registry,
            ),
        )

    def declares(self, plugin_id, capability):
        """Whether this plugin asked for a capability in its manifest.

        The one place that answers it. Two hosts hand services over -- the
        settings panel and the editor workspace -- and each used to read
        the manifest itself, which is two chances to disagree about what a
        declaration is.

        A plugin core has no record of has declared nothing. That is the
        honest answer rather than a cautious one: contributions arrive from
        loaded plugins, and a loaded plugin has a manifest.
        """
        record = self.records.get(plugin_id)
        if record is None:
            return False
        return capability in (
            record.manifest.requires + record.manifest.optional
        )

    def _record(self, plugin_id):
        if plugin_id not in self.records:
            raise KeyError("Unknown plugin {!r}.".format(plugin_id))
        return self.records[plugin_id]

    def _deactivate_record(self, record):
        """The one boundary where a loaded plugin incarnation ends.

        Authority is retired here rather than in ``disable`` alone, because
        this is reached three ways -- disabled, rediscovered and replaced,
        or found incompatible with the project format -- and only the first
        was taking a plugin's capabilities away. A reload therefore left the
        old incarnation's leases live, which is exactly what the epoch
        exists to prevent.
        """

        plugin_id = record.manifest.id
        if self.capabilityAuthority is not None:
            # Anything the old incarnation left running -- a search on a
            # worker thread, a panel not yet torn down -- still holds
            # capability objects, and those objects ask on every call.
            self.capabilityAuthority.retire_plugin(plugin_id)
        self.registry.remove_plugin(plugin_id)
        if record.driver is not None:
            record.driver.deactivate(record.manifest, record.session)
        record.driver = None
        record.session = None
