"""Stable, mostly Qt-free contracts exposed to Manuskript plugins."""

import re

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping, Optional, Sequence, Union

from manuskript.domain.exporting import ExportArtifact
from manuskript.media_types import MARKDOWN


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


#: Same characters a plugin ID allows, and at least one dot: extension IDs
#: are addressed globally, so they carry their namespace with them.
EXTENSION_ID = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$"
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
        if not EXTENSION_ID.match(self.id) or "." not in self.id:
            raise ValueError(
                "Invalid extension ID {!r}: use a dotted name of letters, "
                "digits, '.', '_' and '-', prefixed with your plugin's "
                "namespace, like 'vendor.notes.panel'.".format(self.id)
            )


@dataclass(frozen=True)
class PluginActivationContext:
    """What a handle's ``activate`` receives, once install has succeeded.

    The entry point stages contributions and can still be refused, so it
    must not leave side effects behind. Anything that connects signals,
    starts timers or touches the world belongs in ``activate``, which only
    runs for a plugin that is installed and staying.
    """

    plugin_id: str
    capability: Callable[[str], Any]


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
class WorkspaceDocument:
    """Portable description of one editable outline document."""

    id: str
    title: str
    kind: str
    text: str = ""
    compile: bool = True
    parent_id: Optional[str] = None


@dataclass(frozen=True)
class EntitySnapshot:
    id: str
    type: str
    title: str
    path: str
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StoryReferenceValue:
    kind: str
    id: str


@dataclass(frozen=True)
class TemporalPointValue:
    axis: str
    reference: Optional[StoryReferenceValue] = None
    value: Any = None


@dataclass(frozen=True)
class TemporalIntervalValue:
    valid_from: Optional[TemporalPointValue] = None
    valid_until: Optional[TemporalPointValue] = None


@dataclass(frozen=True)
class AssertionTermValue:
    reference: Optional[StoryReferenceValue] = None
    value: Any = None
    is_reference: bool = False


@dataclass(frozen=True)
class AssertionSnapshot:
    id: str
    subject: StoryReferenceValue
    predicate: str
    object: AssertionTermValue
    qualifiers: Mapping[str, Any]
    document_id: str
    source_start: int
    source_end: int
    anchor: str = ""
    note: str = ""
    canon_state: str = "canon"
    validity: Optional[TemporalIntervalValue] = None


@dataclass(frozen=True)
class ChronologySnapshot:
    subject: StoryReferenceValue
    kind: str
    assertion_id: str
    start: Optional[str] = None
    end: Optional[str] = None
    related_to: Optional[StoryReferenceValue] = None
    label: str = ""


@dataclass(frozen=True)
class TemporalDiagnosticSnapshot:
    assertion_id: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class TemporalFactSnapshot:
    assertion: AssertionSnapshot
    status: str
    reason: str = ""


@dataclass(frozen=True)
class RuleSummarySnapshot:
    id: str
    label: str


@dataclass(frozen=True)
class RuleEvidenceSnapshot:
    assertion_id: str
    document_id: str
    source_start: int
    source_end: int
    role: str = "evidence"


@dataclass(frozen=True)
class RuleFindingSnapshot:
    id: str
    rule_id: str
    rule_label: str
    outcome: str
    severity: str
    message: str
    evidence: tuple[RuleEvidenceSnapshot, ...]


@dataclass(frozen=True)
class RuleReportSnapshot:
    findings: tuple[RuleFindingSnapshot, ...]
    evaluated_rule_ids: tuple[str, ...]


@dataclass(frozen=True)
class RuleDiagnosticSnapshot:
    document_id: str
    path: str
    message: str
    severity: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class RevisionPassSnapshot:
    id: str
    label: str


@dataclass(frozen=True)
class DocumentRevisionWorkflowSnapshot:
    document_id: str
    title: str
    states: Mapping[str, str]


@dataclass(frozen=True)
class ProseOccurrenceSnapshot:
    document_id: str
    source_start: int
    source_end: int
    excerpt: str


@dataclass(frozen=True)
class CountedPatternSnapshot:
    pattern: str
    count: int
    occurrences: tuple[ProseOccurrenceSnapshot, ...] = ()


@dataclass(frozen=True)
class SimilarNameSnapshot:
    first: str
    second: str
    distance: int
    similarity: float


@dataclass(frozen=True)
class DocumentProseMetricsSnapshot:
    document_id: str
    title: str
    word_count: int
    sentence_lengths: tuple[int, ...]
    paragraph_lengths: tuple[int, ...]
    dialogue_word_ratio: float
    punctuation: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ProseAnalysisSnapshot:
    documents: tuple[DocumentProseMetricsSnapshot, ...]
    repeated_phrases: tuple[CountedPatternSnapshot, ...]
    repeated_openings: tuple[CountedPatternSnapshot, ...]
    nearby_repetitions: tuple[CountedPatternSnapshot, ...]
    passive_candidates: tuple[CountedPatternSnapshot, ...]
    filler_phrases: tuple[CountedPatternSnapshot, ...]
    spelling_mixtures: tuple[CountedPatternSnapshot, ...]
    similar_names: tuple[SimilarNameSnapshot, ...]


@dataclass(frozen=True)
class ReferenceOccurrenceSnapshot:
    source_document_id: str
    source_path: str
    source_start: int
    source_end: int
    raw_target: str
    display_text: Optional[str]
    resolution: str
    resolved_target_id: Optional[str] = None
    resolved_target_path: Optional[str] = None


@dataclass(frozen=True)
class ReferenceSuggestionSnapshot:
    document_id: str
    target: str
    title: str
    path: str


@dataclass(frozen=True)
class AssertionDiagnosticSnapshot:
    document_id: str
    path: str
    message: str
    severity: str
    source_start: int
    source_end: int


@dataclass(frozen=True)
class MorphologySchemaSnapshot:
    id: str
    label: str
    language_tag: str
    version: str


@dataclass(frozen=True)
class EditorWorkspaceContext:
    """Project-scoped capabilities supplied to an editor workspace.

    The service objects deliberately use capability-based interfaces. Plugins
    receive only their project-file namespace, a guarded outline gateway, and
    an editor factory instead of the main window or raw project models.
    """

    plugin_id: str
    project_file: str
    selected_item_ids: tuple[str, ...]
    files: Any
    outline: Any
    editors: Any
    show_status: Callable[..., None]
    close_workspace: Callable[[], None]
    capability: Callable[[str], Any]


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
    source_format: str = MARKDOWN


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
class IndexCardStyleContribution:
    """Draw cork board index cards in a style of the plugin's own design.

    ``style_factory`` takes no arguments and must return an
    ``IndexCardStyle``. The base class owns the drawing sequence shared by
    every card; a style supplies only geometry and the parts that make it
    look like itself, so styles stay small and cannot skip a phase.
    """

    descriptor: ExtensionDescriptor
    style_factory: Callable[..., Any]


@dataclass(frozen=True)
class PluginSettingsContribution:
    """Render plugin-owned settings in the plugin manager's details pane.

    The details pane shows application-owned identity above (name, version,
    author, location) and this widget below. Manuskript never draws its own
    controls in that lower region: whatever appears there belongs to the
    selected plugin, so nothing one plugin configures can surface under
    another.

    ``widget_factory`` receives ``(PluginSettingsContext, parent)`` and must
    return a QWidget. The Qt type is checked by the UI host so the stable
    registration contract remains importable without Qt.
    """

    descriptor: ExtensionDescriptor
    widget_factory: Callable[..., Any]


@dataclass(frozen=True)
class PluginSettingsContext:
    """Capabilities offered to one plugin's settings panel.

    Like EditorWorkspaceContext, the services are capability interfaces
    scoped to the plugin rather than the registry or main window.

    ``capability`` is the same negotiation as ``api.capability`` during
    registration, moved to where a widget can actually be built: plugins
    register before there is a main window, so a UI service cannot be handed
    over then. It refuses any name the manifest did not declare, so core
    stops pushing services at panels that never asked for one.
    """

    plugin_id: str
    option_store: Any
    edit_options: Callable[..., None]
    show_status: Callable[..., None]
    capability: Callable[[str], Any]


@dataclass(frozen=True)
class EditorWorkspaceContribution:
    """Add a project-scoped workspace to Manuskript's editor area.

    ``workspace_factory`` receives ``(EditorWorkspaceContext, parent)`` and
    must return a QWidget. The Qt type is checked by the UI host so the stable
    registration contract remains importable without Qt.
    """

    descriptor: ExtensionDescriptor
    workspace_factory: Callable[..., Any]
    action_label: str = ""
    shortcut: str = ""
    minimum_selection: int = 0
    maximum_selection: Optional[int] = None

    def __post_init__(self):
        minimum = int(self.minimum_selection)
        maximum = (
            None
            if self.maximum_selection is None
            else int(self.maximum_selection)
        )
        if minimum < 0:
            raise ValueError(
                "Workspace minimum_selection cannot be negative."
            )
        if maximum is not None and maximum < minimum:
            raise ValueError(
                "Workspace maximum_selection cannot be smaller than its "
                "minimum_selection."
            )
        if not callable(self.workspace_factory):
            raise ValueError(
                "Editor workspaces require a callable workspace_factory."
            )
        object.__setattr__(self, "minimum_selection", minimum)
        object.__setattr__(self, "maximum_selection", maximum)
        object.__setattr__(
            self,
            "action_label",
            str(self.action_label or self.descriptor.name),
        )


@dataclass(frozen=True)
class ContentSignature:
    """A pattern core matches so a plugin need not read foreign documents.

    A page type has to be recognised before any property marks an item as
    belonging to it, and only the plugin knows its own format. Declaring the
    format instead of inspecting the text resolves that: the plugin remains
    the authority on what its pages look like, while core does the matching
    and the plugin is never handed a document it does not own.

    All declared parts must match. Patterns are regular expressions applied
    with MULTILINE, against text normalised to newline endings.
    """

    starts_with: str = ""
    ends_with: str = ""
    contains: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(
            self,
            "contains",
            tuple(str(value) for value in self.contains),
        )
        if not any((self.starts_with, self.ends_with, self.contains)):
            raise ValueError(
                "A content signature must declare at least one pattern."
            )


@dataclass(frozen=True)
class PageTypeContribution:
    descriptor: ExtensionDescriptor
    property_label: str
    #: Declarative recognition. Preferred: core matches it, so the plugin
    #: never receives the text of a document that is not its own.
    signature: Optional[ContentSignature] = None
    #: Escape hatch for formats a signature cannot express. Receives a
    #: bounded window of the document, not the whole of it.
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


@dataclass(frozen=True)
class TransformContribution:
    """Middleware over whatever produces a format.

    A transform takes content in one media type and returns it in the same
    one: a table-of-contents injector, a link rewriter, a house-style pass.
    It converts nothing, which is why it is not a converter, and it does not
    produce the format either -- it waits for something that does and adds
    to the result.

    Transforms stack. Several may apply to one media type and they run in
    priority order, highest first, between the producer and the output.
    """

    descriptor: ExtensionDescriptor
    media_type: str
    engine_factory: Callable[[], Any]
    options: tuple[OptionField, ...] = ()
    options_view_factory: Optional[Callable[..., Any]] = None
    priority: int = 0

    def __post_init__(self):
        object.__setattr__(self, "media_type", str(self.media_type).strip())
        object.__setattr__(self, "options", tuple(self.options))
        if not self.media_type:
            raise ValueError(
                "Transforms must name the media type they take and return."
            )

    def applies_to(self, media_type):
        """Whether this transform handles content of that media type.

        Here rather than in the registry, for the reason HTML augmentations
        answer for their own scope: a catalogue that filters by one kind of
        context ends up with a method per kind of caller.
        """
        return self.media_type == media_type
        if not self.media_type:
            raise ValueError(
                "Transforms must name the media type they take and return."
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


@dataclass(frozen=True)
class ConversionRequest:
    """One conversion about to happen, described so contributions can judge it.

    A value rather than a pile of arguments, so that a contribution answers
    one question -- does this apply to me -- and a later fact about a
    rendering can be added here without changing what every contribution
    implements.
    """

    source_format: str
    target_format: str
    page_type: Optional[str] = None


@dataclass(frozen=True)
class ConversionAugmentationContribution:
    """Something one format should additionally mean when it becomes another.

    Not a transform and not a converter. A converter turns one format into
    another and there is one of it; a transform is middleware over content
    that stays in the same format. This adds to what an existing conversion
    understands -- lists written ``1)``, a footnote convention, a spoiler box
    -- and every route that performs that conversion picks it up.

    The formats are **declared, not implied**. There is no contribution kind
    per destination, because that would make one format privileged and every
    other reachable only through something more generic: two classes of media
    type, native and not. A route here is ordinary data drawn from the same
    vocabulary a manifest declares, so augmenting Markdown to BBCode is the
    same act as augmenting Markdown to HTML.

    ``augmentation_factory`` returns whatever the converter for that route
    accepts, and what that is belongs to the route rather than to this
    contract -- a ``markdown.Extension`` where python-markdown performs the
    conversion. The contract here is the route and the ordering; what the
    engine takes is documented with the engine.

    ``page_types`` is the scope. Empty means every document; naming page types
    narrows it to documents of those types.

    Augmentations stack, highest ``priority`` first, so an addition that must
    see the source before another can say so.
    """

    descriptor: ExtensionDescriptor
    source_format: str
    target_format: str
    augmentation_factory: Callable[[], Any]
    page_types: tuple[str, ...] = ()
    priority: int = 0

    def __post_init__(self):
        object.__setattr__(
            self, "source_format", str(self.source_format).strip(),
        )
        object.__setattr__(
            self, "target_format", str(self.target_format).strip(),
        )
        object.__setattr__(
            self,
            "page_types",
            tuple(
                str(value).strip()
                for value in self.page_types
                if str(value).strip()
            ),
        )
        if not self.source_format or not self.target_format:
            raise ValueError(
                "Conversion augmentation {} must name the formats it "
                "augments between.".format(self.descriptor.id)
            )
        if self.augmentation_factory is None:
            raise ValueError(
                "Conversion augmentation {} needs a factory.".format(
                    self.descriptor.id
                )
            )

    def applies_to(self, request):
        """Whether this augmentation belongs in that conversion.

        The route must match, and the scope must admit the document. Asked of
        the contribution because the contribution is where both were
        declared; a registry answering it would need one such method per kind
        of context a caller might be in.
        """
        if request is None:
            return False
        if (
            self.source_format != request.source_format
            or self.target_format != request.target_format
        ):
            return False
        if not self.page_types:
            return True
        return (
            request.page_type is not None
            and request.page_type in self.page_types
        )


Contribution = Union[
    ExportContribution,
    ConversionAugmentationContribution,
    ImportContribution,
    ConversionContribution,
    ProjectPanelContribution,
    PluginSettingsContribution,
    IndexCardStyleContribution,
    EditorWorkspaceContribution,
    PageTypeContribution,
    PageRendererContribution,
    TransformContribution,
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
