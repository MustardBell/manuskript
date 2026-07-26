import os
import shutil
import subprocess
from enum import IntEnum

from PyQt5.QtCore import QSettings


class ExternalToolAvailability(IntEnum):
    MISSING = 0
    CUSTOM = 1
    SYSTEM = 2


class ExternalToolPaths:
    """Persist custom executable paths behind a narrow settings port."""

    LEGACY_NAMES = {
        "pandoc": ("Pandoc",),
    }

    def __init__(self, settings=None):
        self._settings = settings if settings is not None else QSettings()

    def get(self, tool_name):
        canonical_name = self._canonical_name(tool_name)
        for candidate in (
            canonical_name,
            *self.LEGACY_NAMES.get(canonical_name, ()),
        ):
            key = self._key(candidate)
            if self._settings.contains(key):
                return self._settings.value(key, "")
        return ""

    def set(self, tool_name, path):
        self._settings.setValue(
            self._key(self._canonical_name(tool_name)),
            path,
        )

    @staticmethod
    def _canonical_name(tool_name):
        return tool_name.casefold()

    @staticmethod
    def _key(tool_name):
        return "Exporters/{}_customPath".format(tool_name)


class ExternalTool:
    """Resolve and execute one optional command-line dependency."""

    def __init__(
        self,
        name,
        command,
        *,
        paths=None,
        which=shutil.which,
        exists=os.path.exists,
        check_output=subprocess.check_output,
    ):
        self.name = name
        self.command = command
        self.paths = (
            paths if paths is not None else ExternalToolPaths()
        )
        self._which = which
        self._exists = exists
        self._check_output = check_output

    @property
    def custom_path(self):
        return self.paths.get(self.name)

    @custom_path.setter
    def custom_path(self, path):
        self.paths.set(self.name, path)

    @property
    def system_path(self):
        return self._which(self.command)

    @property
    def availability(self):
        if self.system_path is not None:
            return ExternalToolAvailability.SYSTEM
        if self.custom_path and self._exists(self.custom_path):
            return ExternalToolAvailability.CUSTOM
        return ExternalToolAvailability.MISSING

    @property
    def executable(self):
        if self.availability is ExternalToolAvailability.SYSTEM:
            return self.command
        if self.availability is ExternalToolAvailability.CUSTOM:
            return self.custom_path
        return None

    def run_text(self, arguments, executable=None):
        executable = executable or self.executable
        if executable is None:
            return None
        output = self._check_output([executable] + list(arguments))
        return output.decode("utf-8")
