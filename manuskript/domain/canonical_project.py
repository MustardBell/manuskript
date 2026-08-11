"""Qt-free representation of everything a Manuskript project owns.

The canonical project is deliberately a faithful interchange model before it
is an elegant story model.  A codec can populate it without importing Qt, a
UI adapter can project it into the current item models, and a different codec
can persist it again.  Raw source is retained on records so an unchanged
round trip need not rewrite author-controlled text.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Tuple, Union


ProjectContent = Union[str, bytes]


@dataclass(frozen=True)
class SourceLocation:
    path: str
    field: str = ""
    line: Optional[int] = None


@dataclass(frozen=True)
class ProjectIssue:
    """An invalid or suspicious source construct that was not discarded."""

    severity: str
    message: str
    source: SourceLocation


@dataclass(frozen=True)
class MetadataField:
    """One ordered metadata entry.

    A tuple of these is used instead of a mapping because historical MMD
    files may contain duplicate field names and their order is meaningful for
    byte-preserving output.
    """

    name: str
    value: str


@dataclass(frozen=True)
class LabelRecord:
    name: str
    color: str = ""


@dataclass(frozen=True)
class CharacterRecord:
    id: str
    name: str
    fields: Tuple[MetadataField, ...] = ()
    custom_fields: Tuple[MetadataField, ...] = ()
    color: str = ""
    source_path: str = ""
    raw_source: Optional[str] = field(default=None, compare=False)

    def value(self, name: str, default: str = "") -> str:
        for entry in reversed(self.fields):
            if entry.name == name:
                return entry.value
        return default


@dataclass(frozen=True)
class RevisionRecord:
    document_id: str
    timestamp: str
    text: str


@dataclass(frozen=True)
class OutlineDocument:
    id: str
    title: str
    kind: str
    text: str
    metadata: Tuple[MetadataField, ...] = ()
    children: Tuple["OutlineDocument", ...] = ()
    source_path: str = ""
    source_format: str = "mmd"
    raw_source: Optional[str] = field(default=None, compare=False)

    def metadata_value(self, name: str, default: str = "") -> str:
        for entry in reversed(self.metadata):
            if entry.name == name:
                return entry.value
        return default

    def walk(self) -> Iterable["OutlineDocument"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(frozen=True)
class WorldRecord:
    fields: Tuple[MetadataField, ...]
    children: Tuple["WorldRecord", ...] = ()

    def value(self, name: str, default: str = "") -> str:
        for entry in reversed(self.fields):
            if entry.name == name:
                return entry.value
        return default


@dataclass(frozen=True)
class PlotStepRecord:
    fields: Tuple[MetadataField, ...]

    def value(self, name: str, default: str = "") -> str:
        for entry in reversed(self.fields):
            if entry.name == name:
                return entry.value
        return default


@dataclass(frozen=True)
class PlotRecord:
    fields: Tuple[MetadataField, ...]
    character_ids: Tuple[str, ...] = ()
    steps: Tuple[PlotStepRecord, ...] = ()

    def value(self, name: str, default: str = "") -> str:
        for entry in reversed(self.fields):
            if entry.name == name:
                return entry.value
        return default


@dataclass(frozen=True)
class LegacyCell:
    text: str = ""
    color: str = ""
    children: Tuple[Tuple["LegacyCell", ...], ...] = ()


@dataclass(frozen=True)
class LegacyModel:
    """Generic Qt-free representation of a version-0 item-model XML file."""

    name: str
    horizontal_headers: Tuple[str, ...]
    vertical_headers: Tuple[str, ...]
    rows: Tuple[Tuple[LegacyCell, ...], ...]
    raw_source: bytes = field(compare=False, default=b"")


@dataclass(frozen=True)
class PreservedProjectFile:
    """A project file not interpreted by the selected codec."""

    path: str
    content: ProjectContent
    reason: str = "unknown"


@dataclass(frozen=True)
class CanonicalProject:
    """Complete persisted project state, independent of UI technology."""

    format_version: int
    zipped: bool = False
    metadata: Tuple[MetadataField, ...] = ()
    summary: Tuple[MetadataField, ...] = ()
    labels: Tuple[LabelRecord, ...] = ()
    statuses: Tuple[str, ...] = ()
    characters: Tuple[CharacterRecord, ...] = ()
    outline: Tuple[OutlineDocument, ...] = ()
    world: Tuple[WorldRecord, ...] = ()
    plots: Tuple[PlotRecord, ...] = ()
    revisions: Tuple[RevisionRecord, ...] = ()
    settings_source: Optional[ProjectContent] = None
    plugin_files: Tuple[PreservedProjectFile, ...] = ()
    unknown_files: Tuple[PreservedProjectFile, ...] = ()
    legacy_models: Tuple[LegacyModel, ...] = ()
    issues: Tuple[ProjectIssue, ...] = ()
    source_files: Tuple[PreservedProjectFile, ...] = field(
        default=(), compare=False, repr=False
    )

    def documents(self) -> Iterable[OutlineDocument]:
        for document in self.outline:
            yield from document.walk()

    def file(self, path: str) -> Optional[PreservedProjectFile]:
        for project_file in self.plugin_files + self.unknown_files:
            if project_file.path == path:
                return project_file
        return None

    @classmethod
    def from_mapping(
        cls,
        format_version: int,
        values: Mapping[str, Any],
        **kwargs: Any
    ) -> "CanonicalProject":
        """Small adapter for importers that already expose named sections."""

        return cls(
            format_version=format_version,
            metadata=tuple(
                MetadataField(str(name), str(value))
                for name, value in values.items()
            ),
            **kwargs
        )
