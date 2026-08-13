"""Execution drivers behind the language-neutral plugin runtime manifest."""

import hashlib
import importlib
import logging
import sys
import types

from dataclasses import dataclass

from manuskript.plugins.api import PluginActivationContext
from manuskript.plugins.capabilities import capability_catalogue
from manuskript.plugins.capability_rpc import (
    CapabilityRpcRouter,
    portable_capability_methods,
)
from manuskript.plugins.contracts import (
    CONTRIBUTION_CONTRACTS,
    PLUGIN_PROTOCOL_VERSION,
    ContractPortability,
    ContributionKind,
)
from manuskript.plugins.errors import (
    PluginCompatibilityError,
    PluginLoadError,
    PluginProtocolError,
    PluginRegistrationError,
)
from manuskript.plugins.rpc import RpcProcess
from manuskript.plugins.specification import protocol_document
from manuskript.plugins.runtimes import (
    ProcessRuntime,
    PythonRuntime,
    RuntimeAvailability,
    RuntimeKind,
)
from manuskript.plugins.values import PortableArtifact, api_value_codec


LOGGER = logging.getLogger(__name__)
_PROTOCOL_SPECIFICATION = protocol_document()
MAX_REMOTE_CONTRIBUTIONS = _PROTOCOL_SPECIFICATION["limits"][
    "max_remote_contributions"
]


class PluginDriver:
    """One implementation of plugin load, activation, and teardown."""

    kind = None

    def availability(self, manifest):
        raise NotImplementedError

    def load(self, manifest, registrar, context=None):
        raise NotImplementedError

    def activate(self, manifest, session, registrar):
        raise NotImplementedError

    def deactivate(self, manifest, session):
        raise NotImplementedError

    def required_capabilities(self, manifest):
        return manifest.requires

    def optional_capabilities(self, manifest):
        return manifest.optional

    def project_changed(self, manifest, session, generation, project_format):
        """Announce a project identity change to a live driver session."""

    def publish_event(self, manifest, session, topic, payload):
        """Publish one project event when this driver supports events."""


@dataclass
class PythonDriverSession:
    module_prefix: str
    handle: object = None
    closed: bool = False


class PythonPluginDriver(PluginDriver):
    kind = RuntimeKind.PYTHON

    def availability(self, manifest):
        if not isinstance(manifest.runtime, PythonRuntime):
            return RuntimeAvailability(
                False,
                error="Python driver received a non-Python runtime.",
            )
        return RuntimeAvailability(True)

    def load(self, manifest, registrar, context=None):
        module_prefix = self._module_prefix(manifest)
        session = PythonDriverSession(module_prefix)
        try:
            entry = self._load_entry_point(manifest, module_prefix)
            session.handle = entry(registrar)
            return session
        except Exception:
            self._remove_modules(module_prefix)
            session.closed = True
            raise

    def activate(self, manifest, session, registrar):
        handle = session.handle
        if handle is None or not hasattr(handle, "activate"):
            return
        handle.activate(PluginActivationContext(
            plugin_id=manifest.id,
            capability=registrar.capability,
        ))

    def deactivate(self, manifest, session):
        if session is None or session.closed:
            return
        handle = session.handle
        if handle is not None and hasattr(handle, "deactivate"):
            try:
                handle.deactivate()
            except Exception:
                LOGGER.exception(
                    "Plugin %s failed while deactivating.",
                    manifest.id,
                )
        self._remove_modules(session.module_prefix)
        session.handle = None
        session.closed = True

    @staticmethod
    def _load_entry_point(manifest, module_prefix):
        package = types.ModuleType(module_prefix)
        package.__path__ = [str(manifest.root)]
        package.__package__ = module_prefix
        sys.modules[module_prefix] = package
        module_name = "{}.{}".format(
            module_prefix,
            manifest.runtime.module,
        )
        try:
            module = importlib.import_module(module_name)
        except Exception:
            PythonPluginDriver._remove_modules(module_prefix)
            raise
        entry = getattr(module, manifest.runtime.callable, None)
        if not callable(entry):
            raise PluginLoadError(
                "Entry point {}:{} is not callable.".format(
                    manifest.runtime.module,
                    manifest.runtime.callable,
                )
            )
        return entry

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


@dataclass(frozen=True)
class PluginDriverContext:
    api_version: int
    project_format: object = None
    project_generation: int = 0
    generation_source: object = None
    capability_resolver: object = None


@dataclass
class ProcessDriverSession:
    rpc: RpcProcess
    router: object = None
    initialized: bool = False
    activated: bool = False
    closed: bool = False


class ProcessPluginDriver(PluginDriver):
    """Bind portable contribution declarations to one RPC process."""

    kind = RuntimeKind.PROCESS

    def __init__(self, initialize_timeout=10.0, request_timeout=30.0):
        self.initialize_timeout = float(initialize_timeout)
        self.request_timeout = float(request_timeout)
        if min(self.initialize_timeout, self.request_timeout) <= 0:
            raise ValueError("Process driver deadlines must be positive.")

    def availability(self, manifest):
        if not isinstance(manifest.runtime, ProcessRuntime):
            return RuntimeAvailability(
                False,
                error="Process driver received a non-process runtime.",
            )
        if manifest.runtime.protocol_version != PLUGIN_PROTOCOL_VERSION:
            return RuntimeAvailability(
                False,
                error=(
                    "Plugin {} requires RPC protocol {}, but Manuskript "
                    "provides protocol {}."
                ).format(
                    manifest.id,
                    manifest.runtime.protocol_version,
                    PLUGIN_PROTOCOL_VERSION,
                ),
            )
        catalogue = capability_catalogue()
        unsupported = tuple(
            name for name in manifest.requires
            if (
                name in catalogue
                and catalogue[name].portability
                is not ContractPortability.PORTABLE
            )
        )
        if unsupported:
            return RuntimeAvailability(
                False,
                error=(
                    "Plugin {} requires capabilities that are not available "
                    "to process plugins: {}."
                ).format(manifest.id, ", ".join(unsupported)),
            )
        return manifest.runtime.availability(manifest.root)

    def required_capabilities(self, manifest):
        return self._portable_capabilities(manifest.requires)

    def optional_capabilities(self, manifest):
        return self._portable_capabilities(manifest.optional)

    @staticmethod
    def _portable_capabilities(names):
        catalogue = capability_catalogue()
        return tuple(
            name for name in names
            if (
                name not in catalogue
                or catalogue[name].portability
                is ContractPortability.PORTABLE
            )
        )

    def load(self, manifest, registrar, context=None):
        context = context or PluginDriverContext(manifest.api_version)
        availability = self.availability(manifest)
        if not availability.available:
            raise PluginLoadError(availability.error)
        declared_capabilities = (
            self.required_capabilities(manifest)
            + self.optional_capabilities(manifest)
        )
        generation_source = context.generation_source or (
            lambda: context.project_generation
        )
        capability_resolver = context.capability_resolver or (
            lambda name: registrar.capability(name)
        )
        router = CapabilityRpcRouter(
            manifest.id,
            declared_capabilities,
            capability_resolver,
            generation_source,
        )
        rpc = RpcProcess(
            manifest.id,
            availability.command,
            manifest.root,
            request_handler=router.handle,
        )
        session = ProcessDriverSession(rpc, router=router)
        try:
            result = rpc.request(
                "initialize",
                self._initialize_params(manifest, context),
                timeout=self.initialize_timeout,
            )
            declarations = self._initialize_result(manifest, result)
            for declaration, operations in declarations:
                registrar.register_declaration(
                    declaration,
                    self._bind_handlers(session, declaration, operations),
                )
            session.initialized = True
            return session
        except Exception:
            rpc.terminate(timeout=0.5)
            session.closed = True
            raise

    def activate(self, manifest, session, registrar):
        session.rpc.notify("initialized")
        session.activated = True

    def deactivate(self, manifest, session):
        if session is None or session.closed:
            return
        if session.initialized:
            try:
                session.rpc.request(
                    "deactivate",
                    timeout=min(1.0, self.request_timeout),
                )
            except Exception:
                LOGGER.exception(
                    "Plugin %s failed while deactivating RPC session.",
                    manifest.id,
                )
        session.rpc.shutdown(timeout=0.5)
        session.closed = True

    def project_changed(self, manifest, session, generation, project_format):
        if session is None or session.closed:
            return
        session.router.invalidate_subscriptions()
        session.rpc.notify("project/changed", {
            "project_generation": generation,
            "project_format": project_format,
        })

    def publish_event(self, manifest, session, topic, payload):
        if session is None or session.closed:
            return
        for notification in session.router.event_notifications(
            topic, payload
        ):
            session.rpc.notify("event/publish", notification)

    @staticmethod
    def _initialize_params(manifest, context):
        codec = api_value_codec()
        catalogue = capability_catalogue()
        granted = tuple(
            name for name in manifest.requires + manifest.optional
            if (
                name in catalogue
                and catalogue[name].portability
                is ContractPortability.PORTABLE
            )
        )
        return {
            "plugin": {
                "id": manifest.id,
                "version": manifest.version,
            },
            "host": {
                "api_version": context.api_version,
                "protocol_version": PLUGIN_PROTOCOL_VERSION,
                "project_format": context.project_format,
                "project_generation": context.project_generation,
            },
            "capabilities": portable_capability_methods(granted),
            "contribution_kinds": {
                contract.kind.value: contract.portability.value
                for contract in CONTRIBUTION_CONTRACTS
            },
            "value_schema": codec.schema_document,
        }

    @staticmethod
    def _initialize_result(manifest, result):
        if not isinstance(result, dict):
            raise PluginProtocolError(
                "Plugin initialize result must be an object."
            )
        expected = {
            "plugin_id", "api_version", "protocol_version", "contributions"
        }
        if set(result) != expected:
            raise PluginProtocolError(
                "Plugin initialize result fields must be exactly: {}."
                .format(", ".join(sorted(expected)))
            )
        if result["plugin_id"] != manifest.id:
            raise PluginCompatibilityError(
                "Plugin process identified itself as {!r}, expected {!r}."
                .format(result["plugin_id"], manifest.id)
            )
        if result["api_version"] != manifest.api_version:
            raise PluginCompatibilityError(
                "Plugin process initialized API {}, expected API {}."
                .format(result["api_version"], manifest.api_version)
            )
        if result["protocol_version"] != PLUGIN_PROTOCOL_VERSION:
            raise PluginCompatibilityError(
                "Plugin process initialized protocol {}, expected {}."
                .format(
                    result["protocol_version"],
                    PLUGIN_PROTOCOL_VERSION,
                )
            )
        contributions = result["contributions"]
        if not isinstance(contributions, list):
            raise PluginProtocolError(
                "Plugin initialize contributions must be an array."
            )
        if len(contributions) > MAX_REMOTE_CONTRIBUTIONS:
            raise PluginProtocolError(
                "Plugin initialize exceeds {} contributions."
                .format(MAX_REMOTE_CONTRIBUTIONS)
            )
        codec = api_value_codec()
        decoded = []
        for item in contributions:
            if not isinstance(item, dict) or set(item) != {
                "declaration", "operations"
            }:
                raise PluginProtocolError(
                    "Remote contribution fields must be declaration and "
                    "operations."
                )
            declaration = codec.decode(item["declaration"])
            from manuskript.plugins.api import ContributionDeclaration
            if not isinstance(declaration, ContributionDeclaration):
                raise PluginProtocolError(
                    "Remote contribution did not decode to a declaration."
                )
            contract = next(
                contract
                for contract in CONTRIBUTION_CONTRACTS
                if contract.kind is declaration.kind
            )
            if contract.portability is not ContractPortability.PORTABLE:
                raise PluginRegistrationError(
                    "Remote plugin {} cannot register {}: {}"
                    .format(
                        manifest.id,
                        declaration.kind.value,
                        contract.reason,
                    )
                )
            operations = item["operations"]
            if (
                not isinstance(operations, list)
                or not all(
                    isinstance(operation, str) and operation
                    for operation in operations
                )
                or len(operations) != len(set(operations))
            ):
                raise PluginProtocolError(
                    "Remote contribution operations must be unique strings."
                )
            decoded.append((declaration, tuple(operations)))
        return tuple(decoded)

    def _bind_handlers(self, session, declaration, operations):
        kind = declaration.kind
        allowed = _REMOTE_OPERATIONS[kind]
        unknown = set(operations) - set(allowed)
        missing = set(allowed.required) - set(operations)
        if unknown or missing:
            details = []
            if unknown:
                details.append("unknown {}".format(", ".join(sorted(unknown))))
            if missing:
                details.append("missing {}".format(", ".join(sorted(missing))))
            raise PluginRegistrationError(
                "Remote {} operations are invalid: {}."
                .format(kind.value, "; ".join(details))
            )
        contribution_id = declaration.descriptor.id
        handlers = {}
        if "export" in operations:
            handlers["engine_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "import_document" in operations:
            handlers["engine_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "convert" in operations:
            handlers["engine_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "transform" in operations:
            handlers["engine_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "detect" in operations:
            handlers["detector"] = lambda source: self._call(
                session, contribution_id, "detect", (source,)
            )
        if "parse" in operations:
            handlers["parser_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "render" in operations:
            handlers["renderer_factory"] = lambda: _RemoteEngine(
                self, session, contribution_id
            )
        if "activation_warning" in operations:
            handlers["activation_warning"] = lambda source: self._call(
                session, contribution_id, "activation_warning", (source,)
            )
        if "ui_open" in operations:
            scope = (
                "project"
                if kind is ContributionKind.PROJECT_PANEL
                else "settings"
            )
            handlers["widget_factory"] = lambda _context, parent=None: (
                _build_remote_ui_widget(
                    _RemoteUiController(
                        self, session, contribution_id
                    ),
                    scope,
                    parent,
                )
            )
        if "invoke" in operations:
            handlers["invoke"] = lambda: self._call(
                session, contribution_id, "invoke", ()
            )
        if "analyze" in operations:
            handlers["analyze"] = lambda request: self._call(
                session,
                contribution_id,
                "analyze",
                (request,),
                timeout=min(5.0, self.request_timeout),
            )
        if "cancel_analysis" in operations:
            handlers["cancel_analysis"] = lambda analysis_id: (
                self._notify_contribution(
                    session,
                    contribution_id,
                    "cancel_analysis",
                    (analysis_id,),
                )
            )
        return handlers

    def _call(
            self, session, contribution_id, operation, arguments,
            timeout=None):
        codec = api_value_codec()
        result = session.rpc.request(
            "contribution/call",
            {
                "contribution_id": contribution_id,
                "operation": operation,
                "arguments": codec.encode(tuple(arguments)),
            },
            timeout=(self.request_timeout if timeout is None else timeout),
        )
        return codec.decode(result)

    @staticmethod
    def _notify_contribution(
            session, contribution_id, operation, arguments):
        codec = api_value_codec()
        session.rpc.notify("contribution/notify", {
            "contribution_id": contribution_id,
            "operation": operation,
            "arguments": codec.encode(tuple(arguments)),
        })


@dataclass(frozen=True)
class _RemoteOperations:
    names: tuple
    required: tuple

    def __iter__(self):
        return iter(self.names)


_REMOTE_OPERATIONS = {
    ContributionKind(kind): _RemoteOperations(
        tuple(contract["operations"]),
        tuple(contract["required"]),
    )
    for kind, contract in _PROTOCOL_SPECIFICATION["contributions"].items()
    if contract["portability"] == ContractPortability.PORTABLE.value
}


class _RemoteEngine:
    def __init__(self, driver, session, contribution_id):
        self._driver = driver
        self._session = session
        self._contribution_id = contribution_id

    def export(self, snapshot, options):
        from manuskript.domain.exporting import ExportArtifact

        result = self._call("export", snapshot, options)
        if not isinstance(result, PortableArtifact):
            return result
        return ExportArtifact(
            result.content.unpack(),
            result.suggested_name,
            result.content.media_type,
        )

    def import_document(self, source, options):
        return self._call("import_document", source, options)

    def convert(self, content, source_format, target_format, options):
        from manuskript.plugins.api import ConversionArtifact

        result = self._call(
            "convert", content, source_format, target_format, options
        )
        if not isinstance(result, PortableArtifact):
            return result
        return ConversionArtifact(
            result.content.unpack(),
            result.suggested_name,
            result.content.media_type,
            result.warnings,
        )

    def transform(self, content, media_type, options):
        return self._call("transform", content, media_type, options)

    def parse(self, source):
        return self._call("parse", source)

    def render(self, *arguments):
        return self._call("render", *arguments)

    def _call(self, operation, *arguments):
        return self._driver._call(
            self._session,
            self._contribution_id,
            operation,
            arguments,
        )


class _RemoteUiController:
    def __init__(self, driver, session, contribution_id):
        self._driver = driver
        self._session = session
        self._contributionId = contribution_id

    def open(self, scope, session_id):
        return self._driver._call(
            self._session,
            self._contributionId,
            "ui_open",
            (scope, session_id),
        )

    def event(self, event):
        return self._driver._call(
            self._session,
            self._contributionId,
            "ui_event",
            (event,),
        )

    def close(self, session_id):
        codec = api_value_codec()
        self._session.rpc.notify("contribution/notify", {
            "contribution_id": self._contributionId,
            "operation": "ui_close",
            "arguments": codec.encode((session_id,)),
        })


def _build_remote_ui_widget(controller, scope, parent):
    # Imported only when a window asks to display the declaration. Drivers
    # and the portable plugin contract remain importable without Qt.
    from manuskript.ui.plugins.declarative_ui import DeclarativeUiWidget

    return DeclarativeUiWidget(controller, scope, parent=parent)
