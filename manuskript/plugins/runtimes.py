"""Plugin runtime declarations independent of the runtime implementation."""

import os
import re
import shutil
import sys

from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Mapping, Union


PYTHON_MODULE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
PYTHON_CALLABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PLATFORMS = ("linux", "windows", "macos")


class RuntimeKind(str, Enum):
    PYTHON = "python"
    PROCESS = "process"


@dataclass(frozen=True)
class PythonRuntime:
    module: str
    callable: str
    kind: RuntimeKind = RuntimeKind.PYTHON

    def __post_init__(self):
        module = str(self.module).strip()
        callable_name = str(self.callable).strip()
        if not PYTHON_MODULE.fullmatch(module):
            raise ValueError("Python runtime module is invalid.")
        if not PYTHON_CALLABLE.fullmatch(callable_name):
            raise ValueError("Python runtime callable is invalid.")
        object.__setattr__(self, "module", module)
        object.__setattr__(self, "callable", callable_name)
        object.__setattr__(self, "kind", RuntimeKind.PYTHON)


@dataclass(frozen=True)
class RuntimeAvailability:
    available: bool
    command: tuple = ()
    error: str = ""


@dataclass(frozen=True)
class ProcessRuntime:
    protocol_version: int
    commands: Mapping[str, tuple]
    kind: RuntimeKind = RuntimeKind.PROCESS

    def __post_init__(self):
        try:
            if isinstance(self.protocol_version, bool):
                raise TypeError
            protocol_version = int(self.protocol_version)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Process runtime protocol_version must be an integer."
            ) from error
        if protocol_version < 1:
            raise ValueError(
                "Process runtime protocol_version must be positive."
            )
        if not isinstance(self.commands, Mapping) or not self.commands:
            raise ValueError(
                "Process runtime commands must be a nonempty object."
            )
        unknown = set(self.commands) - set(PLATFORMS)
        if unknown:
            raise ValueError(
                "Process runtime commands contain unknown platforms: {}."
                .format(", ".join(sorted(unknown)))
            )
        commands = {}
        for platform, command in self.commands.items():
            if not isinstance(command, (list, tuple)) or not command:
                raise ValueError(
                    "Process runtime command for {} must be a nonempty "
                    "argument array.".format(platform)
                )
            if any(not isinstance(argument, str) for argument in command):
                raise ValueError(
                    "Process runtime command arguments must be strings."
                )
            arguments = tuple(command)
            if any(not argument or "\x00" in argument for argument in arguments):
                raise ValueError(
                    "Process runtime command arguments cannot be empty or "
                    "contain NUL."
                )
            _validate_executable(arguments[0])
            commands[str(platform)] = arguments
        object.__setattr__(self, "protocol_version", protocol_version)
        object.__setattr__(
            self,
            "commands",
            MappingProxyType(commands),
        )
        object.__setattr__(self, "kind", RuntimeKind.PROCESS)

    def command_for(self, plugin_root, platform=None):
        """Resolve an exact argv without invoking a shell."""
        platform = platform or current_platform()
        command = self.commands.get(platform)
        if command is None:
            raise ValueError(
                "Plugin does not provide a {} process command."
                .format(platform)
            )
        executable = command[0]
        if not _is_plugin_path(executable):
            return command
        relative = PurePosixPath(executable.replace("\\", "/"))
        root = Path(plugin_root).resolve()
        resolved = (root / Path(*relative.parts)).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise ValueError(
                "Process runtime executable escapes the plugin directory."
            ) from error
        return (str(resolved),) + command[1:]

    def availability(self, plugin_root, platform=None):
        """Explain whether the current host can start this runtime."""
        platform = platform or current_platform()
        try:
            command = self.command_for(plugin_root, platform)
        except ValueError as error:
            return RuntimeAvailability(False, error=str(error))
        executable = command[0]
        if _is_plugin_path(self.commands[platform][0]):
            path = Path(executable)
            if not path.is_file():
                return RuntimeAvailability(
                    False,
                    command,
                    "Plugin executable does not exist: {}.".format(path),
                )
            if platform != "windows" and not os.access(str(path), os.X_OK):
                return RuntimeAvailability(
                    False,
                    command,
                    "Plugin executable is not executable: {}.".format(path),
                )
        elif shutil.which(executable) is None:
            return RuntimeAvailability(
                False,
                command,
                "Required runtime executable {!r} was not found."
                .format(executable),
            )
        return RuntimeAvailability(True, command)


PluginRuntimeDescriptor = Union[PythonRuntime, ProcessRuntime]


def current_platform():
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    raise ValueError(
        "Unsupported plugin runtime platform {!r}.".format(sys.platform)
    )


def _is_plugin_path(executable):
    return (
        executable.startswith(".")
        or "/" in executable
        or "\\" in executable
    )


def _validate_executable(executable):
    if not _is_plugin_path(executable):
        if ":" in executable:
            raise ValueError(
                "Process runtime executable must be a command name or a "
                "relative plugin path."
            )
        return
    path = PurePosixPath(executable.replace("\\", "/"))
    if (
        path.is_absolute()
        or any(part in ("", "..") for part in path.parts)
        or any(":" in part for part in path.parts)
    ):
        raise ValueError(
            "Process runtime executable must stay inside the plugin "
            "directory."
        )
