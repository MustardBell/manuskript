"""Stable, mostly Qt-free contracts exposed to Manuskript plugins."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping, Sequence


PLUGIN_API_VERSION = 1


class OptionKind(str, Enum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    CHOICE = "choice"


@dataclass(frozen=True)
class OptionField:
    key: str
    label: str
    kind: OptionKind = OptionKind.STRING
    default: Any = None
    description: str = ""
    choices: tuple[tuple[str, Any], ...] = ()
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self):
        if not self.key or not self.label:
            raise ValueError("Plugin option keys and labels are required.")
        if self.kind is OptionKind.CHOICE and not self.choices:
            raise ValueError(
                "Choice plugin options must declare at least one choice."
            )


@dataclass(frozen=True)
class ExtensionDescriptor:
    id: str
    name: str
    description: str = ""
    icon: str = ""
    extensions: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.id or not self.name:
            raise ValueError("Extension IDs and names are required.")


@dataclass(frozen=True)
class OutlineSnapshot:
    id: str
    title: str
    kind: str
    text: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    children: tuple["OutlineSnapshot", ...] = ()


@dataclass(frozen=True)
class ProjectSnapshot:
    project_file: str
    metadata: Mapping[str, Any]
    outline: OutlineSnapshot


@dataclass(frozen=True)
class ExportArtifact:
    content: str | bytes
    suggested_name: str
    media_type: str = "application/octet-stream"


@dataclass(frozen=True)
class ImportNode:
    title: str
    kind: str = "md"
    text: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    children: tuple["ImportNode", ...] = ()


@dataclass(frozen=True)
class ImportResult:
    nodes: tuple[ImportNode, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExportContribution:
    descriptor: ExtensionDescriptor
    engine_factory: Callable[[], Any]
    options: tuple[OptionField, ...] = ()
    options_view_factory: Callable[..., Any] | None = None


@dataclass(frozen=True)
class ImportContribution:
    descriptor: ExtensionDescriptor
    engine_factory: Callable[[], Any]
    file_filter: str
    source_kind: str = "file"
    options: tuple[OptionField, ...] = ()
    options_view_factory: Callable[..., Any] | None = None

    def __post_init__(self):
        if self.source_kind not in ("file", "folder"):
            raise ValueError(
                "Importer source_kind must be 'file' or 'folder'."
            )


@dataclass(frozen=True)
class ConversionContribution:
    descriptor: ExtensionDescriptor
    engine_factory: Callable[[], Any]
    source_formats: tuple[str, ...]
    target_formats: tuple[str, ...]
    options: tuple[OptionField, ...] = ()


@dataclass(frozen=True)
class ProjectPanelContribution:
    descriptor: ExtensionDescriptor
    widget_factory: Callable[..., Any]
    default_file: str

    def __post_init__(self):
        if not self.default_file:
            raise ValueError(
                "Project panels must declare a default raw project file."
            )


class MarkupMode(str, Enum):
    AUGMENT = "augment"
    REPLACE = "replace"


@dataclass(frozen=True)
class MarkupContribution:
    descriptor: ExtensionDescriptor
    mode: MarkupMode
    highlighter_factory: Callable[..., Any]
    behavior_factory: Callable[..., Any] | None = None


Contribution = (
    ExportContribution
    | ImportContribution
    | ConversionContribution
    | ProjectPanelContribution
    | MarkupContribution
)


def contribution_descriptor(contribution: Contribution):
    descriptor = getattr(contribution, "descriptor", None)
    if not isinstance(descriptor, ExtensionDescriptor):
        raise TypeError(
            "Plugin contributions must expose an ExtensionDescriptor."
        )
    return descriptor


def normalize_options(
    fields: Sequence[OptionField],
    values: Mapping[str, Any] | None = None,
):
    """Return JSON-compatible option values with declared defaults."""
    supplied = dict(values or {})
    return {
        option.key: supplied.get(option.key, option.default)
        for option in fields
    }
