import re
from dataclasses import dataclass
from pathlib import PurePosixPath


PLUGIN_ID = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
PLUGIN_ROOT = "plugins"


def _validate_plugin_id(plugin_id):
    plugin_id = str(plugin_id)
    if not PLUGIN_ID.fullmatch(plugin_id):
        raise ValueError("Invalid plugin ID {!r}.".format(plugin_id))
    return plugin_id


def _validate_relative_path(path):
    path = str(path).replace("\\", "/")
    candidate = PurePosixPath(path)
    if (
        not path
        or candidate.is_absolute()
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise ValueError(
            "Plugin project paths must be safe relative paths."
        )
    return candidate.as_posix()


class ProjectPluginData:
    """Own portable raw files under ``plugins/<plugin-id>/``."""

    def __init__(self):
        self._files = {}

    def load_project_files(self, files):
        prefix = PLUGIN_ROOT + "/"
        self._files = {
            str(path).replace("\\", "/"): content
            for path, content in files.items()
            if str(path).replace("\\", "/").startswith(prefix)
        }

    def project_files(self):
        return tuple(sorted(self._files.items()))

    def namespace(self, plugin_id, on_change=None):
        return PluginFileNamespace(
            self,
            _validate_plugin_id(plugin_id),
            on_change=on_change,
        )


class PluginFileNamespace:
    """Restrict one plugin to its own portable project-file namespace."""

    def __init__(self, store, plugin_id, on_change=None):
        self._store = store
        self.plugin_id = plugin_id
        self._on_change = on_change or (lambda: None)

    def paths(self):
        prefix = self._prefix + "/"
        return tuple(
            path[len(prefix):]
            for path in sorted(self._store._files)
            if path.startswith(prefix)
        )

    def read(self, path, default=None):
        return self._store._files.get(
            self._project_path(path),
            default,
        )

    def write(self, path, content):
        if not isinstance(content, (str, bytes)):
            raise TypeError(
                "Plugin project files must contain text or bytes."
            )
        project_path = self._project_path(path)
        if self._store._files.get(project_path) == content:
            return False
        self._store._files[project_path] = content
        self._on_change()
        return True

    def delete(self, path):
        project_path = self._project_path(path)
        if project_path not in self._store._files:
            return False
        del self._store._files[project_path]
        self._on_change()
        return True

    @property
    def _prefix(self):
        return "{}/{}".format(PLUGIN_ROOT, self.plugin_id)

    def _project_path(self, path):
        return "{}/{}".format(
            self._prefix,
            _validate_relative_path(path),
        )


@dataclass(frozen=True)
class PluginProjectContext:
    plugin_id: str
    project_file: str
    files: PluginFileNamespace
    default_file: str
    show_status: object
    capability: object = None
