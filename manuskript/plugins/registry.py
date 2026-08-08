from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from manuskript.plugins.api import (
    Contribution,
    ConversionContribution,
    EditorWorkspaceContribution,
    ExportContribution,
    HtmlAugmentationContribution,
    ImportContribution,
    IndexCardStyleContribution,
    MarkupContribution,
    PageRendererContribution,
    PageTypeContribution,
    PluginSettingsContribution,
    ProjectPanelContribution,
    TransformContribution,
    contribution_descriptor,
)
from manuskript.plugins.errors import (
    PluginRegistrationError,
    PluginScopeError,
)


class ContributionKind(str, Enum):
    EXPORTER = "exporter"
    IMPORTER = "importer"
    CONVERTER = "converter"
    PROJECT_PANEL = "project_panel"
    SETTINGS_PANEL = "settings_panel"
    INDEX_CARD_STYLE = "index_card_style"
    EDITOR_WORKSPACE = "editor_workspace"
    PAGE_TYPE = "page_type"
    PAGE_RENDERER = "page_renderer"
    MARKUP = "markup"
    TRANSFORM = "transform"
    HTML_AUGMENTATION = "html_augmentation"


CONTRIBUTION_TYPES = {
    ContributionKind.EXPORTER: ExportContribution,
    ContributionKind.IMPORTER: ImportContribution,
    ContributionKind.CONVERTER: ConversionContribution,
    ContributionKind.PROJECT_PANEL: ProjectPanelContribution,
    ContributionKind.SETTINGS_PANEL: PluginSettingsContribution,
    ContributionKind.INDEX_CARD_STYLE: IndexCardStyleContribution,
    ContributionKind.EDITOR_WORKSPACE: EditorWorkspaceContribution,
    ContributionKind.PAGE_TYPE: PageTypeContribution,
    ContributionKind.PAGE_RENDERER: PageRendererContribution,
    ContributionKind.MARKUP: MarkupContribution,
    ContributionKind.TRANSFORM: TransformContribution,
    ContributionKind.HTML_AUGMENTATION: HtmlAugmentationContribution,
}


#: Where each kind of contribution names the media types it works with.
#:
#: ExportContribution is deliberately absent: its ``output_format`` falls
#: back to the descriptor ID, so it doubles as an identifier and cannot be
#: read as a media type without guessing which one it is.
MEDIA_TYPE_FIELDS = {
    ContributionKind.CONVERTER: ("source_formats", "target_formats"),
    ContributionKind.PAGE_RENDERER: ("target_formats",),
    ContributionKind.TRANSFORM: ("media_type",),
}


def contribution_media_types(kind, contribution):
    """Every media type one contribution names."""
    names = set()
    for attribute in MEDIA_TYPE_FIELDS.get(ContributionKind(kind), ()):
        value = getattr(contribution, attribute, ())
        if isinstance(value, str):
            if value:
                names.add(value)
        else:
            names.update(str(entry) for entry in value)
    return names


@dataclass(frozen=True)
class RegisteredContribution:
    plugin_id: str
    kind: ContributionKind
    contribution: Contribution

    @property
    def id(self):
        return contribution_descriptor(self.contribution).id


class PluginRegistrar:
    """Stage one plugin's contributions before atomically installing them."""

    def __init__(self, plugin_id, capabilities=None):
        self.plugin_id = plugin_id
        self._contributions = []
        self._capabilities = dict(capabilities or {})

    def capability(self, name):
        """A service this plugin declared and core granted.

        Refuses anything undeclared rather than returning it, so a plugin
        cannot quietly widen the surface its manifest advertises.
        """
        try:
            return self._capabilities[name]
        except KeyError:
            raise PluginScopeError(
                "Plugin {} did not declare capability {!r} in its "
                "manifest.".format(self.plugin_id, name)
            ) from None

    @property
    def contributions(self):
        return tuple(self._contributions)

    def register_exporter(self, contribution):
        self._add(ContributionKind.EXPORTER, contribution)

    def register_importer(self, contribution):
        self._add(ContributionKind.IMPORTER, contribution)

    def register_converter(self, contribution):
        self._add(ContributionKind.CONVERTER, contribution)

    def register_project_panel(self, contribution):
        self._add(ContributionKind.PROJECT_PANEL, contribution)

    def register_settings_panel(self, contribution):
        self._add(ContributionKind.SETTINGS_PANEL, contribution)

    def register_index_card_style(self, contribution):
        self._add(ContributionKind.INDEX_CARD_STYLE, contribution)

    def register_editor_workspace(self, contribution):
        self._add(ContributionKind.EDITOR_WORKSPACE, contribution)

    def register_page_type(self, contribution):
        self._add(ContributionKind.PAGE_TYPE, contribution)

    def register_page_renderer(self, contribution):
        self._add(ContributionKind.PAGE_RENDERER, contribution)

    def register_markup(self, contribution):
        self._add(ContributionKind.MARKUP, contribution)

    def register_transform(self, contribution):
        self._add(ContributionKind.TRANSFORM, contribution)

    def register_html_augmentation(self, contribution):
        self._add(ContributionKind.HTML_AUGMENTATION, contribution)

    def _add(self, kind, contribution):
        expected = CONTRIBUTION_TYPES[kind]
        if not isinstance(contribution, expected):
            raise PluginRegistrationError(
                "{} contributions must be {} objects.".format(
                    kind.value,
                    expected.__name__,
                )
            )
        descriptor = contribution_descriptor(contribution)
        if any(
            existing.kind is kind and existing.id == descriptor.id
            for existing in self._contributions
        ):
            raise PluginRegistrationError(
                "Plugin {} registered duplicate {} ID {!r}.".format(
                    self.plugin_id,
                    kind.value,
                    descriptor.id,
                )
            )
        self._contributions.append(
            RegisteredContribution(
                plugin_id=self.plugin_id,
                kind=kind,
                contribution=contribution,
            )
        )


class PluginRegistry:
    """Own all validated contributions, indexed by capability and stable ID."""

    def __init__(self):
        self._by_kind = defaultdict(dict)
        self._by_plugin = defaultdict(list)

    def registrar(self, plugin_id, capabilities=None):
        return PluginRegistrar(plugin_id, capabilities=capabilities)

    def install(self, plugin_id, contributions):
        contributions = tuple(contributions)
        if any(record.plugin_id != plugin_id for record in contributions):
            raise PluginRegistrationError(
                "A plugin cannot install another plugin's contributions."
            )

        collisions = [
            (record.kind.value, record.id)
            for record in contributions
            # A plugin's own records are about to be replaced, so only
            # somebody else holding the ID is a conflict: reinstalling a
            # plugin over itself must not refuse the plugin.
            if record.id in self._by_kind[record.kind]
            and self._by_kind[record.kind][record.id].plugin_id != plugin_id
        ]
        if collisions:
            kind, contribution_id = collisions[0]
            owner = self._by_kind[
                ContributionKind(kind)
            ][contribution_id].plugin_id
            raise PluginRegistrationError(
                "{} ID {!r} is already registered by {}.".format(
                    kind,
                    contribution_id,
                    owner,
                )
            )

        self.remove_plugin(plugin_id)
        for record in contributions:
            self._by_kind[record.kind][record.id] = record
            self._by_plugin[plugin_id].append(record)

    def remove_plugin(self, plugin_id):
        for record in self._by_plugin.pop(plugin_id, ()):
            self._by_kind[record.kind].pop(record.id, None)

    def contributions(self, kind):
        kind = ContributionKind(kind)
        return tuple(
            record.contribution
            for record in self._by_kind[kind].values()
        )

    def records(self, kind):
        kind = ContributionKind(kind)
        return tuple(self._by_kind[kind].values())

    def plugin_records(self, plugin_id, kind=None):
        """Contributions installed by one plugin, in registration order."""
        records = tuple(self._by_plugin.get(plugin_id, ()))
        if kind is None:
            return records
        kind = ContributionKind(kind)
        return tuple(r for r in records if r.kind is kind)

    def owner_of(self, kind, contribution_id):
        """The plugin ID that registered a contribution, or ''."""
        record = self._by_kind[ContributionKind(kind)].get(contribution_id)
        return record.plugin_id if record is not None else ''

    @property
    def exporters(self):
        return self.contributions(ContributionKind.EXPORTER)

    @property
    def importers(self):
        return self.contributions(ContributionKind.IMPORTER)

    @property
    def converters(self):
        return self.contributions(ContributionKind.CONVERTER)

    @property
    def project_panels(self):
        return self.contributions(ContributionKind.PROJECT_PANEL)

    @property
    def settings_panels(self):
        return self.contributions(ContributionKind.SETTINGS_PANEL)

    @property
    def index_card_styles(self):
        return self.contributions(ContributionKind.INDEX_CARD_STYLE)

    @property
    def editor_workspaces(self):
        return self.contributions(ContributionKind.EDITOR_WORKSPACE)

    @property
    def page_types(self):
        return self.contributions(ContributionKind.PAGE_TYPE)

    @property
    def page_renderers(self):
        return self.contributions(ContributionKind.PAGE_RENDERER)

    @property
    def markup(self):
        return self.contributions(ContributionKind.MARKUP)

    @property
    def transforms(self):
        return self.contributions(ContributionKind.TRANSFORM)

    @property
    def html_augmentations(self):
        return self.contributions(ContributionKind.HTML_AUGMENTATION)

    def html_augmentations_for(self, page_type=None):
        """What Markdown additionally means here, highest priority first.

        An augmentation naming no page type applies to every document; one
        naming page types applies to documents of those types. Asking without
        a page type asks for the unrestricted ones, which is what rendering
        an ordinary document wants.
        """
        return tuple(sorted(
            (
                contribution
                for contribution in self.html_augmentations
                if not contribution.page_types
                or (page_type is not None and page_type in contribution.page_types)
            ),
            key=lambda contribution: -contribution.priority,
        ))

    def transforms_for(self, media_type):
        """Middleware over one media type, in the order it runs."""
        return tuple(sorted(
            (
                contribution
                for contribution in self.transforms
                if contribution.media_type == media_type
            ),
            key=lambda value: (
                -value.priority,
                value.descriptor.id,
            ),
        ))
