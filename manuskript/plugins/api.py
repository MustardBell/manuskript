"""Stable, mostly Qt-free contracts exposed to Manuskript plugins."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from manuskript.domain.exporting import ExportArtifact


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
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    section: str = ""

    def __post_init__(self):
        object.__setattr__(self, "kind", OptionKind(self.kind))
        object.__setattr__(self, "choices", tuple(self.choices))
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
class ConversionArtifact:
    content: Union[str, bytes]
    suggested_name: str = "converted.txt"
    media_type: str = "application/octet-stream"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderedDocument:
    html: str
    base_url: str = ""


@dataclass(frozen=True)
class PageExportDocument:
    content: str
    source_format: str = "markdown"


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
    options_view_factory: Optional[Callable[..., Any]] = None
    output_format: str = ""

    def __post_init__(self):
        object.__setattr__(
            self,
            "output_format",
            str(self.output_format or self.descriptor.id),
        )


@dataclass(frozen=True)
class ImportContribution:
    descriptor: ExtensionDescriptor
    engine_factory: Callable[[], Any]
    file_filter: str
    source_kind: str = "file"
    options: tuple[OptionField, ...] = ()
    options_view_factory: Optional[Callable[..., Any]] = None

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
    options_view_factory: Optional[Callable[..., Any]] = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "source_formats",
            tuple(str(value) for value in self.source_formats),
        )
        object.__setattr__(
            self,
            "target_formats",
            tuple(str(value) for value in self.target_formats),
        )
        if not self.source_formats or not self.target_formats:
            raise ValueError(
                "Converters must declare source and target formats."
            )


@dataclass(frozen=True)
class ProjectPanelContribution:
    descriptor: ExtensionDescriptor
    widget_factory: Callable[..., Any]
    default_file: str

    def __post_init__(self):
        path = PurePosixPath(str(self.default_file).replace("\\", "/"))
        if (
            not self.default_file
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in path.parts)
        ):
            raise ValueError(
                "Project panels must declare a safe relative raw "
                "project file."
            )


@dataclass(frozen=True)
class PageTypeContribution:
    descriptor: ExtensionDescriptor
    property_label: str
    detector: Optional[Callable[[str], bool]] = None
    parser_factory: Optional[Callable[[], Any]] = None
    renderer_factory: Optional[Callable[[], Any]] = None
    wizard_factory: Optional[Callable[..., Any]] = None
    activation_warning: Optional[Callable[[str], str]] = None
    item_kinds: tuple[str, ...] = ("md",)

    def __post_init__(self):
        object.__setattr__(
            self,
            "item_kinds",
            tuple(str(value) for value in self.item_kinds),
        )
        if not self.property_label or not self.item_kinds:
            raise ValueError(
                "Page types require a property label and item kind."
            )
        if not any((
            self.parser_factory,
            self.renderer_factory,
            self.wizard_factory,
        )):
            raise ValueError(
                "Page types must provide a parser, renderer, or wizard."
            )


@dataclass(frozen=True)
class PageRendererContribution:
    descriptor: ExtensionDescriptor
    page_type_id: str
    renderer_factory: Callable[[], Any]
    target_formats: tuple[str, ...]
    options: tuple[OptionField, ...] = ()
    options_view_factory: Optional[Callable[..., Any]] = None
    priority: int = 0

    def __post_init__(self):
        object.__setattr__(
            self,
            "target_formats",
            tuple(str(value) for value in self.target_formats),
        )
        object.__setattr__(self, "options", tuple(self.options))
        if not self.page_type_id or not self.target_formats:
            raise ValueError(
                "Page renderers require a page type and target format."
            )


class MarkupMode(str, Enum):
    AUGMENT = "augment"
    REPLACE = "replace"


@dataclass(frozen=True)
class MarkupContribution:
    descriptor: ExtensionDescriptor
    mode: MarkupMode
    highlighter_factory: Callable[..., Any]
    behavior_factory: Optional[Callable[..., Any]] = None
    base_ids: tuple[str, ...] = ("markdown",)

    def __post_init__(self):
        object.__setattr__(self, "mode", MarkupMode(self.mode))
        object.__setattr__(
            self,
            "base_ids",
            tuple(str(value) for value in self.base_ids),
        )
        if self.mode is MarkupMode.AUGMENT and not self.base_ids:
            raise ValueError(
                "Additive markup contributions must declare at least "
                "one compatible base markup ID."
            )


Contribution = Union[
    ExportContribution,
    ImportContribution,
    ConversionContribution,
    ProjectPanelContribution,
    PageTypeContribution,
    PageRendererContribution,
    MarkupContribution,
]


def contribution_descriptor(contribution: Contribution):
    descriptor = getattr(contribution, "descriptor", None)
    if not isinstance(descriptor, ExtensionDescriptor):
        raise TypeError(
            "Plugin contributions must expose an ExtensionDescriptor."
        )
    return descriptor


def normalize_options(
    fields: Sequence[OptionField],
    values: Optional[Mapping[str, Any]] = None,
):
    """Return JSON-compatible option values with declared defaults."""
    supplied = dict(values or {})
    return {
        option.key: supplied.get(option.key, option.default)
        for option in fields
    }
