import json
import re
from dataclasses import dataclass
from pathlib import Path

from manuskript.plugins.errors import PluginManifestError


PLUGIN_ID = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)
ENTRY_POINT = re.compile(
    r"^(?P<module>[A-Za-z_][A-Za-z0-9_.]*):"
    r"(?P<callable>[A-Za-z_][A-Za-z0-9_]*)$"
)


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int
    entry_module: str
    entry_callable: str
    root: Path
    description: str = ""
    author: str = ""
    homepage: str = ""

    @classmethod
    def load(cls, filename):
        filename = Path(filename)
        try:
            value = json.loads(filename.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise PluginManifestError(
                "Cannot read plugin manifest {}: {}".format(
                    filename,
                    error,
                )
            ) from error

        if not isinstance(value, dict):
            raise PluginManifestError(
                "Plugin manifest must contain a JSON object."
            )

        required = (
            "id",
            "name",
            "version",
            "api_version",
            "entry_point",
        )
        missing = [key for key in required if key not in value]
        if missing:
            raise PluginManifestError(
                "Plugin manifest is missing: {}.".format(
                    ", ".join(missing)
                )
            )

        plugin_id = str(value["id"]).strip()
        if not PLUGIN_ID.fullmatch(plugin_id):
            raise PluginManifestError(
                "Invalid plugin ID {!r}.".format(plugin_id)
            )

        name = str(value["name"]).strip()
        version = str(value["version"]).strip()
        if not name or not version:
            raise PluginManifestError(
                "Plugin name and version cannot be empty."
            )

        try:
            api_version = int(value["api_version"])
        except (TypeError, ValueError) as error:
            raise PluginManifestError(
                "Plugin api_version must be an integer."
            ) from error

        entry_point = str(value["entry_point"]).strip()
        match = ENTRY_POINT.fullmatch(entry_point)
        if match is None:
            raise PluginManifestError(
                "Plugin entry_point must use 'module:callable' syntax."
            )

        return cls(
            id=plugin_id,
            name=name,
            version=version,
            api_version=api_version,
            entry_module=match.group("module"),
            entry_callable=match.group("callable"),
            root=filename.parent.resolve(),
            description=str(value.get("description", "")).strip(),
            author=str(value.get("author", "")).strip(),
            homepage=str(value.get("homepage", "")).strip(),
        )
