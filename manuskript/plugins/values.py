"""Canonical values for Plugin API 1.

The codec is deliberately narrower than Python.  Only JSON primitives,
explicit maps/tuples, registered enums, and registered records cross a plugin
transport.  That makes the result implementable without Python and prevents a
new in-process object from becoming an accidental wire promise.
"""

import base64
import binascii
import collections.abc
import math
import typing

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from enum import Enum
from functools import lru_cache
from typing import Mapping

from manuskript.plugins.errors import PluginValueError
from manuskript.plugins.contracts import PLUGIN_API_VERSION
from manuskript.plugins.specification import api_schema_document


WIRE_RECORD_VERSION = 1


class ContentEncoding(str, Enum):
    UTF8 = "utf-8"
    BASE64 = "base64"


@dataclass(frozen=True)
class ContentEnvelope:
    """Text or binary content without relying on a Python ``bytes`` value."""

    content: str
    media_type: str = "application/octet-stream"
    encoding: ContentEncoding = ContentEncoding.UTF8

    def __post_init__(self):
        object.__setattr__(self, "content", str(self.content))
        object.__setattr__(self, "media_type", str(self.media_type).strip())
        object.__setattr__(self, "encoding", ContentEncoding(self.encoding))
        if not self.media_type:
            raise ValueError("Content envelopes require a media type.")
        if self.encoding is ContentEncoding.BASE64:
            try:
                base64.b64decode(
                    self.content.encode("ascii"),
                    validate=True,
                )
            except (UnicodeEncodeError, binascii.Error) as error:
                raise ValueError(
                    "Base64 content envelope contains invalid data."
                ) from error

    @classmethod
    def from_content(cls, content, media_type="application/octet-stream"):
        if isinstance(content, str):
            return cls(content, media_type, ContentEncoding.UTF8)
        if isinstance(content, bytes):
            return cls(
                base64.b64encode(content).decode("ascii"),
                media_type,
                ContentEncoding.BASE64,
            )
        raise TypeError("Content must be text or bytes.")

    def unpack(self):
        if self.encoding is ContentEncoding.UTF8:
            return self.content
        return base64.b64decode(self.content.encode("ascii"), validate=True)


@dataclass(frozen=True)
class PortableArtifact:
    """Transport form of an exported or converted document."""

    content: ContentEnvelope
    suggested_name: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.content, ContentEnvelope):
            raise TypeError("Portable artifacts require a content envelope.")
        object.__setattr__(self, "suggested_name", str(self.suggested_name))
        object.__setattr__(
            self, "warnings", tuple(str(item) for item in self.warnings)
        )


@dataclass(frozen=True)
class ErrorEnvelope:
    """Stable failure data; Python exception types are not a wire contract."""

    code: str
    message: str
    data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        code = str(self.code).strip()
        message = str(self.message)
        if not code:
            raise ValueError("Error envelopes require a stable code.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "data", dict(self.data or {}))


@dataclass(frozen=True)
class ApiValueLimits:
    max_depth: int = 32
    max_items: int = 100000
    max_string_bytes: int = 8 * 1024 * 1024

    def __post_init__(self):
        if min(
            self.max_depth,
            self.max_items,
            self.max_string_bytes,
        ) < 1:
            raise ValueError("API value limits must be positive.")


@dataclass(frozen=True)
class RecordSchema:
    name: str
    version: int
    fields: tuple


@dataclass(frozen=True)
class _RecordBinding:
    schema: RecordSchema
    python_type: type


@dataclass
class _Budget:
    limits: ApiValueLimits
    items: int = 0

    def enter(self, depth):
        if depth > self.limits.max_depth:
            raise PluginValueError(
                "Plugin API value exceeds maximum nesting depth {}."
                .format(self.limits.max_depth)
            )

    def add_items(self, count):
        self.items += count
        if self.items > self.limits.max_items:
            raise PluginValueError(
                "Plugin API value exceeds maximum item count {}."
                .format(self.limits.max_items)
            )

    def string(self, value):
        size = len(value.encode("utf-8"))
        if size > self.limits.max_string_bytes:
            raise PluginValueError(
                "Plugin API string exceeds maximum size {} bytes."
                .format(self.limits.max_string_bytes)
            )


class ApiValueCodec:
    """Encode and decode explicitly bound API records and enums."""

    def __init__(self, record_types=(), enum_types=(), limits=None):
        self.limits = limits or ApiValueLimits()
        self._records_by_name = {}
        self._records_by_type = {}
        self._enums_by_name = {}
        self._enums_by_type = {}
        for name, python_type in record_types:
            self._bind_record(name, python_type)
        for name, python_type in enum_types:
            self._bind_enum(name, python_type)

    @property
    def record_schemas(self):
        return tuple(
            binding.schema
            for _, binding in sorted(self._records_by_name.items())
        )

    @property
    def schema_document(self):
        """The canonical JSON value from which languages build API records."""
        generated = self._binding_schema_document()
        canonical = api_schema_document()
        if generated != canonical:
            raise RuntimeError(
                "Python Plugin API bindings have drifted from the canonical "
                "API-1 value schema."
            )
        return canonical

    def _binding_schema_document(self):
        """Describe Python bindings for validation against the wire model."""
        records = {}
        for name, binding in sorted(self._records_by_name.items()):
            hints = typing.get_type_hints(binding.python_type)
            records[name] = {
                "version": binding.schema.version,
                "fields": [
                    {
                        "name": field.name,
                        "type": self._type_schema(hints[field.name]),
                        "required": (
                            field.default is MISSING
                            and field.default_factory is MISSING
                        ),
                    }
                    for field in fields(binding.python_type)
                ],
            }
        enums = {
            name: [member.value for member in enum_type]
            for name, enum_type in sorted(self._enums_by_name.items())
        }
        return {
            "api_version": PLUGIN_API_VERSION,
            "record_version": WIRE_RECORD_VERSION,
            "records": records,
            "enums": enums,
        }

    def encode(self, value):
        return self._encode(value, _Budget(self.limits), 0)

    def decode(self, value):
        return self._decode(value, _Budget(self.limits), 0)

    def _bind_record(self, name, python_type):
        if not is_dataclass(python_type):
            raise TypeError("Wire records must bind dataclass types.")
        name = str(name).strip()
        if not name or name in self._records_by_name:
            raise ValueError("Wire record names must be unique and nonempty.")
        if python_type in self._records_by_type:
            raise ValueError("A Python type can have only one wire name.")
        schema = RecordSchema(
            name=name,
            version=WIRE_RECORD_VERSION,
            fields=tuple(field.name for field in fields(python_type)),
        )
        binding = _RecordBinding(schema, python_type)
        self._records_by_name[name] = binding
        self._records_by_type[python_type] = binding

    def _bind_enum(self, name, python_type):
        if not issubclass(python_type, Enum):
            raise TypeError("Wire enums must bind Enum types.")
        name = str(name).strip()
        if not name or name in self._enums_by_name:
            raise ValueError("Wire enum names must be unique and nonempty.")
        if python_type in self._enums_by_type:
            raise ValueError("An enum type can have only one wire name.")
        self._enums_by_name[name] = python_type
        self._enums_by_type[python_type] = name

    def _encode(self, value, budget, depth):
        budget.enter(depth)
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise PluginValueError(
                    "Plugin API numbers must be finite."
                )
            return value
        if isinstance(value, str):
            budget.string(value)
            return value
        if isinstance(value, bytes):
            raise PluginValueError(
                "Raw bytes are not portable; use ContentEnvelope."
            )

        enum_name = self._enums_by_type.get(type(value))
        if enum_name is not None:
            return {
                "$kind": "enum",
                "name": enum_name,
                "value": self._encode(value.value, budget, depth + 1),
            }

        binding = self._records_by_type.get(type(value))
        if binding is not None:
            record_fields = fields(value)
            budget.add_items(len(record_fields))
            return {
                "$kind": "record",
                "name": binding.schema.name,
                "version": binding.schema.version,
                "fields": {
                    field.name: self._encode(
                        getattr(value, field.name), budget, depth + 1
                    )
                    for field in record_fields
                },
            }

        if is_dataclass(value):
            raise PluginValueError(
                "Dataclass {} is not a registered Plugin API record."
                .format(type(value).__name__)
            )
        if isinstance(value, tuple):
            budget.add_items(len(value))
            return {
                "$kind": "tuple",
                "items": [
                    self._encode(item, budget, depth + 1)
                    for item in value
                ],
            }
        if isinstance(value, list):
            budget.add_items(len(value))
            return [
                self._encode(item, budget, depth + 1)
                for item in value
            ]
        if isinstance(value, Mapping):
            bad_keys = [key for key in value if not isinstance(key, str)]
            if bad_keys:
                raise PluginValueError(
                    "Plugin API maps require string keys."
                )
            budget.add_items(len(value))
            for key in value:
                budget.string(key)
            return {
                "$kind": "map",
                "items": {
                    key: self._encode(value[key], budget, depth + 1)
                    for key in sorted(value)
                },
            }
        raise PluginValueError(
            "{} is not a portable Plugin API value."
            .format(type(value).__name__)
        )

    def _decode(self, value, budget, depth):
        budget.enter(depth)
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise PluginValueError(
                    "Plugin API numbers must be finite."
                )
            return value
        if isinstance(value, str):
            budget.string(value)
            return value
        if isinstance(value, list):
            budget.add_items(len(value))
            return [
                self._decode(item, budget, depth + 1)
                for item in value
            ]
        if not isinstance(value, dict):
            raise PluginValueError(
                "Wire values must contain JSON-compatible types."
            )

        if not all(isinstance(key, str) for key in value):
            raise PluginValueError(
                "Wire objects require string keys."
            )
        for key in value:
            budget.string(key)

        kind = value.get("$kind")
        if kind == "tuple":
            self._exact_keys(value, {"$kind", "items"}, "tuple")
            items = value["items"]
            if not isinstance(items, list):
                raise PluginValueError("Wire tuple items must be an array.")
            budget.add_items(len(items))
            return tuple(
                self._decode(item, budget, depth + 1)
                for item in items
            )
        if kind == "map":
            self._exact_keys(value, {"$kind", "items"}, "map")
            items = value["items"]
            if not isinstance(items, dict) or not all(
                isinstance(key, str) for key in items
            ):
                raise PluginValueError(
                    "Wire map items must be an object with string keys."
                )
            budget.add_items(len(items))
            return {
                key: self._decode(items[key], budget, depth + 1)
                for key in sorted(items)
            }
        if kind == "enum":
            self._exact_keys(
                value, {"$kind", "name", "value"}, "enum"
            )
            if not isinstance(value["name"], str):
                raise PluginValueError("Wire enum names must be strings.")
            enum_type = self._enums_by_name.get(value["name"])
            if enum_type is None:
                raise PluginValueError(
                    "Unknown Plugin API enum {!r}.".format(value["name"])
                )
            decoded = self._decode(value["value"], budget, depth + 1)
            try:
                return enum_type(decoded)
            except (TypeError, ValueError) as error:
                raise PluginValueError(
                    "Invalid value for Plugin API enum {!r}."
                    .format(value["name"])
                ) from error
        if kind == "record":
            self._exact_keys(
                value,
                {"$kind", "name", "version", "fields"},
                "record",
            )
            if not isinstance(value["name"], str):
                raise PluginValueError("Wire record names must be strings.")
            binding = self._records_by_name.get(value["name"])
            if binding is None:
                raise PluginValueError(
                    "Unknown Plugin API record {!r}.".format(value["name"])
                )
            if value["version"] != binding.schema.version:
                raise PluginValueError(
                    "Unsupported version for Plugin API record {!r}."
                    .format(value["name"])
                )
            supplied = value["fields"]
            if not isinstance(supplied, dict) or not all(
                isinstance(key, str) for key in supplied
            ):
                raise PluginValueError("Wire record fields must be an object.")
            for key in supplied:
                budget.string(key)
            declared_fields = {
                field.name: field
                for field in fields(binding.python_type)
            }
            unknown = set(supplied) - set(declared_fields)
            if unknown:
                raise PluginValueError(
                    "Unknown fields for Plugin API record {!r}: {}."
                    .format(value["name"], ", ".join(sorted(unknown)))
                )
            required = {
                name for name, field in declared_fields.items()
                if field.default is MISSING
                and field.default_factory is MISSING
            }
            missing = required - set(supplied)
            if missing:
                raise PluginValueError(
                    "Missing fields for Plugin API record {!r}: {}."
                    .format(value["name"], ", ".join(sorted(missing)))
                )
            budget.add_items(len(supplied))
            decoded = {
                name: self._decode(item, budget, depth + 1)
                for name, item in supplied.items()
            }
            try:
                return binding.python_type(**decoded)
            except (TypeError, ValueError) as error:
                raise PluginValueError(
                    "Invalid fields for Plugin API record {!r}: {}"
                    .format(value["name"], error)
                ) from error
        raise PluginValueError(
            "Wire objects must be tagged Plugin API maps, records, or enums."
        )

    @staticmethod
    def _exact_keys(value, expected, label):
        actual = set(value)
        if actual != expected:
            raise PluginValueError(
                "Wire {} fields must be exactly: {}."
                .format(label, ", ".join(sorted(expected)))
            )

    def _type_schema(self, annotation):
        if isinstance(annotation, typing.ForwardRef):
            annotation = annotation.__forward_arg__
        if isinstance(annotation, str):
            matches = [
                binding
                for binding in self._records_by_name.values()
                if binding.python_type.__name__ == annotation
            ]
            if len(matches) == 1:
                return {"record": matches[0].schema.name}
            raise TypeError(
                "Unknown portable record annotation {!r}."
                .format(annotation)
            )
        if annotation in (typing.Any, object):
            return "value"
        primitives = {
            type(None): "null",
            bool: "boolean",
            int: "integer",
            float: "number",
            str: "string",
        }
        if annotation in primitives:
            return primitives[annotation]
        if annotation is bytes:
            raise TypeError(
                "Raw bytes cannot appear in a portable record schema."
            )
        record = self._records_by_type.get(annotation)
        if record is not None:
            return {"record": record.schema.name}
        enum_name = self._enums_by_type.get(annotation)
        if enum_name is not None:
            return {"enum": enum_name}

        origin = typing.get_origin(annotation)
        arguments = typing.get_args(annotation)
        if origin is typing.Union:
            non_null = tuple(
                item for item in arguments if item is not type(None)
            )
            if len(non_null) == 1 and len(non_null) != len(arguments):
                return {"optional": self._type_schema(non_null[0])}
            return {
                "one_of": [self._type_schema(item) for item in arguments]
            }
        if origin in (tuple, typing.Tuple):
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return {"sequence": self._type_schema(arguments[0])}
            return {
                "tuple": [self._type_schema(item) for item in arguments]
            }
        if origin in (list, typing.List):
            return {"list": self._type_schema(arguments[0])}
        if origin in (
            dict,
            typing.Dict,
            Mapping,
            collections.abc.Mapping,
        ):
            if len(arguments) != 2 or arguments[0] is not str:
                raise TypeError(
                    "Portable record maps require string keys."
                )
            return {"map": self._type_schema(arguments[1])}
        raise TypeError(
            "Unsupported portable field annotation {!r}.".format(annotation)
        )


def _default_record_types():
    # Imports stay local so api.py can remain independent of codec setup.
    from manuskript.media_types import MediaType
    from manuskript.plugins import api
    from manuskript.plugins.ui_contract import (
        UiChoice,
        UiColumn,
        UiControl,
        UiDocument,
        UiEvent,
        UiItem,
        UiResponse,
    )

    names = (
        "option_field",
        "extension_descriptor",
        "contribution_declaration",
        "outline_snapshot",
        "project_snapshot",
        "workspace_document",
        "entity_snapshot",
        "story_reference",
        "temporal_point",
        "temporal_interval",
        "assertion_term",
        "assertion_snapshot",
        "chronology_snapshot",
        "temporal_diagnostic",
        "temporal_fact",
        "rule_summary",
        "rule_evidence",
        "rule_finding",
        "rule_report",
        "rule_diagnostic",
        "revision_pass",
        "document_revision_workflow",
        "prose_occurrence",
        "counted_pattern",
        "similar_name",
        "document_prose_metrics",
        "prose_analysis",
        "reference_occurrence",
        "reference_suggestion",
        "assertion_diagnostic",
        "morphology_schema",
        "plugin_file",
        "plugin_options",
        "text_range",
        "markup_analysis_request",
        "semantic_span",
        "markup_analysis_result",
        "rendered_document",
        "page_export_document",
        "import_node",
        "import_result",
        "content_signature",
        "conversion_request",
    )
    classes = (
        api.OptionField,
        api.ExtensionDescriptor,
        api.ContributionDeclaration,
        api.OutlineSnapshot,
        api.ProjectSnapshot,
        api.WorkspaceDocument,
        api.EntitySnapshot,
        api.StoryReferenceValue,
        api.TemporalPointValue,
        api.TemporalIntervalValue,
        api.AssertionTermValue,
        api.AssertionSnapshot,
        api.ChronologySnapshot,
        api.TemporalDiagnosticSnapshot,
        api.TemporalFactSnapshot,
        api.RuleSummarySnapshot,
        api.RuleEvidenceSnapshot,
        api.RuleFindingSnapshot,
        api.RuleReportSnapshot,
        api.RuleDiagnosticSnapshot,
        api.RevisionPassSnapshot,
        api.DocumentRevisionWorkflowSnapshot,
        api.ProseOccurrenceSnapshot,
        api.CountedPatternSnapshot,
        api.SimilarNameSnapshot,
        api.DocumentProseMetricsSnapshot,
        api.ProseAnalysisSnapshot,
        api.ReferenceOccurrenceSnapshot,
        api.ReferenceSuggestionSnapshot,
        api.AssertionDiagnosticSnapshot,
        api.MorphologySchemaSnapshot,
        api.PluginFileSnapshot,
        api.PluginOptionsSnapshot,
        api.TextRange,
        api.MarkupAnalysisRequest,
        api.SemanticSpan,
        api.MarkupAnalysisResult,
        api.RenderedDocument,
        api.PageExportDocument,
        api.ImportNode,
        api.ImportResult,
        api.ContentSignature,
        api.ConversionRequest,
    )
    return (
        ("content", ContentEnvelope),
        ("portable_artifact", PortableArtifact),
        ("error", ErrorEnvelope),
        ("media_type", MediaType),
        ("ui_choice", UiChoice),
        ("ui_column", UiColumn),
        ("ui_item", UiItem),
        ("ui_control", UiControl),
        ("ui_document", UiDocument),
        ("ui_event", UiEvent),
        ("ui_response", UiResponse),
    ) + tuple(zip(names, classes))


@lru_cache(maxsize=1)
def api_value_codec():
    from manuskript.plugins import api
    from manuskript.plugins.ui_contract import UiControlKind, UiEventKind

    return ApiValueCodec(
        record_types=_default_record_types(),
        enum_types=(
            ("content_encoding", ContentEncoding),
            ("contribution_kind", api.ContributionKind),
            ("contribution_scope", api.ContributionScope),
            ("option_kind", api.OptionKind),
            ("markup_mode", api.MarkupMode),
            ("text_position_encoding", api.TextPositionEncoding),
            ("semantic_role", api.SemanticRole),
            ("ui_control_kind", UiControlKind),
            ("ui_event_kind", UiEventKind),
        ),
    )
