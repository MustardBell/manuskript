"""Execution drivers behind the language-neutral plugin runtime manifest."""

import hashlib
import importlib
import logging
import sys
import types

from dataclasses import dataclass

from manuskript.plugins.api import PluginActivationContext
from manuskript.plugins.errors import PluginLoadError
from manuskript.plugins.runtimes import (
    PythonRuntime,
    RuntimeAvailability,
    RuntimeKind,
)


LOGGER = logging.getLogger(__name__)


class PluginDriver:
    """One implementation of plugin load, activation, and teardown."""

    kind = None

    def availability(self, manifest):
        raise NotImplementedError

    def load(self, manifest, registrar):
        raise NotImplementedError

    def activate(self, manifest, session, registrar):
        raise NotImplementedError

    def deactivate(self, manifest, session):
        raise NotImplementedError


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

    def load(self, manifest, registrar):
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
