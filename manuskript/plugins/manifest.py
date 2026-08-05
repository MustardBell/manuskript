import json
import re
from dataclasses import dataclass
from pathlib import Path

from manuskript.media_types import MediaType, MediaTypeError
from manuskript.plugins.errors import PluginManifestError


#: The manifest keys that state a promise, and how to say each one.
PROMISE_VERBS = {
    "produces": "produce",
    "consumes": "consume",
    "transforms": "transform",
}

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
    #: Capability names this plugin cannot work without.
    requires: tuple = ()
    #: Formats this plugin knows about. Declaring is not a promise: it says
    #: the name exists and this plugin has an interest in what it resolves
    #: to. Entries are MediaType objects; one naming a format nobody has
    #: introduced carries an identifier and nothing else.
    media_types: tuple = ()
    #: Converts the raw manuscript into these formats itself.
    produces: tuple = ()
    #: Grabs an existing producer of these formats rather than implementing
    #: them.
    consumes: tuple = ()
    #: Middleware: grabs an existing producer of these formats and adds
    #: things on the way out.
    transforms: tuple = ()

    @property
    def promised_media_types(self):
        """Every format this plugin promised something about."""
        return tuple(sorted(
            set(self.produces) | set(self.consumes) | set(self.transforms)
        ))

    @property
    def declared_media_type_ids(self):
        return tuple(media_type.id for media_type in self.media_types)

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

        requires = cls._read_requires(value)
        media_types = cls._read_media_types(value)
        promises = {
            name: cls._read_promise(value, name)
            for name in ("produces", "consumes", "transforms")
        }
        cls._require_declared(plugin_id, media_types, promises)

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
            requires=requires,
            media_types=media_types,
            **promises,
        )

    @staticmethod
    def _read_requires(value):
        """Read declared capability names, rejecting anything unusable.

        A typo here should surface at discovery, where it can be reported
        against the manifest, rather than as a missing service later.
        """
        declared = value.get("requires", ())
        if isinstance(declared, str) or not isinstance(
            declared, (list, tuple)
        ):
            raise PluginManifestError(
                "Plugin requires must be a list of capability names."
            )
        names = []
        for entry in declared:
            if not isinstance(entry, str) or not entry.strip():
                raise PluginManifestError(
                    "Plugin requires entries must be non-empty strings."
                )
            name = entry.strip()
            if name not in names:
                names.append(name)
        return tuple(names)

    @staticmethod
    def _read_media_types(value):
        """Formats this plugin knows about, introduced or merely known.

        A bare string re-declares a format somebody else names, which is
        the common case: a plugin usually cares about formats core already
        has. An object introduces one, and only then are attributes needed.
        """
        declared = value.get("media_types", ())
        if isinstance(declared, str) or not isinstance(
            declared, (list, tuple)
        ):
            raise PluginManifestError(
                "Plugin media_types must be a list of identifiers or "
                "objects."
            )
        media_types = []
        seen = set()
        for entry in declared:
            if isinstance(entry, str):
                identifier, attributes = entry.strip(), {}
            elif isinstance(entry, dict):
                identifier = str(entry.get("id", "")).strip()
                attributes = {
                    "label": str(entry.get("label", "")).strip(),
                    "base": str(entry.get("base", "")).strip(),
                    "textual": bool(entry.get("textual", True)),
                }
            else:
                raise PluginManifestError(
                    "Each media_types entry must be an identifier or an "
                    "object, not {}.".format(type(entry).__name__)
                )
            if not identifier:
                raise PluginManifestError(
                    "A media_types entry needs an identifier."
                )
            if identifier in seen:
                continue
            seen.add(identifier)
            try:
                media_types.append(MediaType(identifier, **attributes))
            except MediaTypeError as error:
                raise PluginManifestError(
                    "Invalid media type {}: {}".format(identifier, error)
                ) from error
        return tuple(media_types)

    @staticmethod
    def _read_promise(value, key):
        declared = value.get(key, ())
        if isinstance(declared, str) or not isinstance(
            declared, (list, tuple)
        ):
            raise PluginManifestError(
                "Plugin {} must be a list of media type identifiers."
                .format(key)
            )
        names = []
        for entry in declared:
            if not isinstance(entry, str) or not entry.strip():
                raise PluginManifestError(
                    "Plugin {} entries must be non-empty media type "
                    "identifiers.".format(key)
                )
            name = entry.strip()
            if name not in names:
                names.append(name)
        return tuple(names)

    @staticmethod
    def _require_declared(plugin_id, media_types, promises):
        """A promise about an undeclared format refuses the plugin.

        Both facts are in the manifest, so this is settled at discovery and
        the plugin's code is never imported. Declaring without promising is
        fine and useful; promising without declaring is a manifest that
        contradicts itself.
        """
        declared = {media_type.id for media_type in media_types}
        for key, names in sorted(promises.items()):
            undeclared = [name for name in names if name not in declared]
            if undeclared:
                raise PluginManifestError(
                    "Plugin {} promises to {} {}, which it does not "
                    "declare in media_types.".format(
                        plugin_id,
                        PROMISE_VERBS[key],
                        ", ".join(sorted(undeclared)),
                    )
                )
