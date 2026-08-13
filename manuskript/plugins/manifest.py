import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from manuskript.media_types import MediaType, MediaTypeError
from manuskript.plugins.errors import PluginManifestError
from manuskript.plugins.runtimes import (
    PluginRuntimeDescriptor,
    ProcessRuntime,
    PythonRuntime,
)


#: The manifest keys that state a promise, and how to say each one.
PROMISE_VERBS = {
    "produces": "produce",
    "consumes": "consume",
    "transforms": "transform",
}


def _shape_error(label, missing, unknown):
    parts = []
    if missing:
        parts.append("missing {}".format(", ".join(sorted(missing))))
    if unknown:
        parts.append("unknown {}".format(", ".join(sorted(unknown))))
    return "{} fields are invalid: {}.".format(label, "; ".join(parts))


PLUGIN_ID = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
)


@dataclass(frozen=True)
class ProjectFormatCompatibility:
    """The project formats a plugin agrees to run against.

    An absent maximum is deliberately not called unconditional support: it
    is a declaration of tentative forward compatibility that can still be
    bounded in a later plugin release when a future format is known.
    """

    minimum: int
    tested_through: int
    maximum: Optional[int] = None
    declared: bool = True

    def supports(self, version):
        try:
            version = int(version)
        except (TypeError, ValueError):
            return False
        return (
            version >= self.minimum
            and (self.maximum is None or version <= self.maximum)
        )

    def explicitly_supports(self, version):
        return self.supports(version) and int(version) <= self.tested_through

    def is_tentative(self, version):
        return self.supports(version) and not self.explicitly_supports(version)

    @property
    def label(self):
        if not self.declared:
            return "not declared; all formats tentative"
        explicit = (
            str(self.minimum)
            if self.minimum == self.tested_through
            else "{}–{}".format(self.minimum, self.tested_through)
        )
        if self.maximum == self.tested_through:
            return explicit + " only"
        if self.maximum is None:
            return explicit + "; later formats tentative"
        return "{}; {}–{} tentative".format(
            explicit, self.tested_through + 1, self.maximum
        )


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int
    runtime: PluginRuntimeDescriptor
    root: Path
    project_formats: ProjectFormatCompatibility
    description: str = ""
    author: str = ""
    homepage: str = ""
    #: Capability names this plugin cannot work without.
    requires: tuple = ()
    #: Capability names the plugin can use when the current host/project
    #: provides them. Missing optional capabilities never prevent loading.
    optional: tuple = ()
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
            "runtime",
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

        runtime = cls._read_runtime(value["runtime"])

        requires = cls._read_capabilities(value, "requires")
        project_formats = cls._read_project_formats(value)
        optional = tuple(
            name for name in cls._read_capabilities(value, "optional")
            if name not in requires
        )
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
            runtime=runtime,
            root=filename.parent.resolve(),
            project_formats=project_formats,
            description=str(value.get("description", "")).strip(),
            author=str(value.get("author", "")).strip(),
            homepage=str(value.get("homepage", "")).strip(),
            requires=requires,
            optional=optional,
            media_types=media_types,
            **promises,
        )

    def supports_project_format(self, version):
        return self.project_formats.supports(version)

    @staticmethod
    def _read_runtime(value):
        if not isinstance(value, dict):
            raise PluginManifestError(
                "Plugin runtime must be an object."
            )
        kind = value.get("kind")
        try:
            if kind == "python":
                expected = {"kind", "module", "callable"}
                unknown = set(value) - expected
                missing = expected - set(value)
                if unknown or missing:
                    raise ValueError(
                        _shape_error("Python runtime", missing, unknown)
                    )
                return PythonRuntime(
                    module=value["module"],
                    callable=value["callable"],
                )
            if kind == "process":
                expected = {"kind", "protocol_version", "commands"}
                unknown = set(value) - expected
                missing = expected - set(value)
                if unknown or missing:
                    raise ValueError(
                        _shape_error("Process runtime", missing, unknown)
                    )
                return ProcessRuntime(
                    protocol_version=value["protocol_version"],
                    commands=value["commands"],
                )
            raise ValueError(
                "Plugin runtime kind must be 'python' or 'process'."
            )
        except (TypeError, ValueError) as error:
            raise PluginManifestError(str(error)) from error

    @staticmethod
    def _read_project_formats(value):
        if "project_formats" not in value:
            # Absence grants no explicit support. Tentative loading keeps the
            # omission visible without pretending a hard maximum was stated.
            return ProjectFormatCompatibility(0, -1, None, False)
        declared = value.get("project_formats")
        if not isinstance(declared, dict):
            raise PluginManifestError(
                "Plugin project_formats must be an object with a minimum "
                "and an optional maximum."
            )
        unknown = set(declared) - {
            "minimum", "tested_through", "maximum"
        }
        if unknown:
            raise PluginManifestError(
                "Plugin project_formats contains unknown fields: {}."
                .format(", ".join(sorted(unknown)))
            )
        missing = [
            name for name in ("minimum", "tested_through")
            if name not in declared
        ]
        if missing:
            raise PluginManifestError(
                "Plugin project_formats requires: {}."
                .format(", ".join(missing))
            )

        def version(name, required=False):
            raw = declared.get(name)
            if raw is None and not required:
                return None
            if isinstance(raw, bool) or not isinstance(raw, int):
                raise PluginManifestError(
                    "Plugin project_formats {} must be a non-negative "
                    "integer.".format(name)
                )
            if raw < 0:
                raise PluginManifestError(
                    "Plugin project_formats {} must be a non-negative "
                    "integer.".format(name)
                )
            return raw

        minimum = version("minimum", required=True)
        tested_through = version("tested_through", required=True)
        maximum = version("maximum")
        if tested_through < minimum:
            raise PluginManifestError(
                "Plugin project_formats tested_through cannot be below "
                "minimum."
            )
        if maximum is not None and maximum < minimum:
            raise PluginManifestError(
                "Plugin project_formats maximum cannot be below minimum."
            )
        if maximum is not None and tested_through > maximum:
            raise PluginManifestError(
                "Plugin project_formats tested_through cannot exceed "
                "maximum."
            )
        return ProjectFormatCompatibility(
            minimum, tested_through, maximum
        )

    @staticmethod
    def _read_capabilities(value, key):
        """Read declared capability names, rejecting anything unusable.

        A typo here should surface at discovery, where it can be reported
        against the manifest, rather than as a missing service later.
        """
        declared = value.get(key, ())
        if isinstance(declared, str) or not isinstance(
            declared, (list, tuple)
        ):
            raise PluginManifestError(
                "Plugin {} must be a list of capability names.".format(key)
            )
        names = []
        for entry in declared:
            if not isinstance(entry, str) or not entry.strip():
                raise PluginManifestError(
                    "Plugin {} entries must be non-empty strings.".format(
                        key
                    )
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
