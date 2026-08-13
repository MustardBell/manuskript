from collections import defaultdict
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields
from types import MappingProxyType

from manuskript.plugins.api import (
    Contribution,
    ContributionDeclaration,
    CommandContribution,
    ConversionContribution,
    EditorWorkspaceContribution,
    ExportContribution,
    ConversionAugmentationContribution,
    ImportContribution,
    IndexCardStyleContribution,
    MarkupContribution,
    NativeMarkupContribution,
    PageRendererContribution,
    PageTypeContribution,
    PluginSettingsContribution,
    ProjectPanelContribution,
    TransformContribution,
    contribution_descriptor,
)
from manuskript.plugins.contracts import ContributionKind
from manuskript.plugins.errors import (
    PluginRegistrationError,
    PluginScopeError,
)
from manuskript.plugins.values import api_value_codec

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
    ContributionKind.NATIVE_MARKUP: NativeMarkupContribution,
    ContributionKind.TRANSFORM: TransformContribution,
    ContributionKind.CONVERSION_AUGMENTATION: (
        ConversionAugmentationContribution
    ),
    ContributionKind.COMMAND: CommandContribution,
}


#: Executable bindings supplied by the Python driver or an RPC proxy. Every
#: other dataclass field is portable declaration data.
CONTRIBUTION_HANDLER_FIELDS = {
    ContributionKind.EXPORTER: (
        "engine_factory", "options_view_factory",
    ),
    ContributionKind.IMPORTER: (
        "engine_factory", "options_view_factory",
    ),
    ContributionKind.CONVERTER: (
        "engine_factory", "options_view_factory",
    ),
    ContributionKind.PROJECT_PANEL: ("widget_factory",),
    ContributionKind.SETTINGS_PANEL: ("widget_factory",),
    ContributionKind.INDEX_CARD_STYLE: ("style_factory",),
    ContributionKind.EDITOR_WORKSPACE: ("workspace_factory",),
    ContributionKind.PAGE_TYPE: (
        "detector",
        "parser_factory",
        "renderer_factory",
        "wizard_factory",
        "activation_warning",
    ),
    ContributionKind.PAGE_RENDERER: (
        "renderer_factory", "options_view_factory",
    ),
    ContributionKind.MARKUP: (
        "analyze", "cancel_analysis",
    ),
    ContributionKind.NATIVE_MARKUP: (
        "highlighter_factory", "behavior_factory",
    ),
    ContributionKind.TRANSFORM: (
        "engine_factory", "options_view_factory",
    ),
    ContributionKind.CONVERSION_AUGMENTATION: (
        "augmentation_factory",
    ),
    ContributionKind.COMMAND: ("invoke",),
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


def _id_namespace(kind):
    """Kinds whose IDs address the same user-facing routing slot."""

    kind = ContributionKind(kind)
    if kind in (ContributionKind.MARKUP, ContributionKind.NATIVE_MARKUP):
        return (ContributionKind.MARKUP, ContributionKind.NATIVE_MARKUP)
    return (kind,)


def contribution_media_types(kind, contribution):
    """Every media type one contribution names."""
    names = set()
    configuration = (
        contribution.configuration
        if isinstance(contribution, ContributionDeclaration)
        else None
    )
    for attribute in MEDIA_TYPE_FIELDS.get(ContributionKind(kind), ()):
        value = (
            configuration.get(attribute, ())
            if configuration is not None
            else getattr(contribution, attribute, ())
        )
        if isinstance(value, str):
            if value:
                names.add(value)
        else:
            names.update(str(entry) for entry in value)
    return names


@dataclass(frozen=True)
class ContributionBinding:
    """Local executable handlers attached to one portable declaration."""

    declaration: ContributionDeclaration
    handlers: object
    contribution: Contribution = field(init=False)

    def __post_init__(self):
        if not isinstance(self.handlers, Mapping) or not all(
            isinstance(name, str) for name in self.handlers
        ):
            raise PluginRegistrationError(
                "Contribution handlers must be a string-keyed map."
            )
        handlers = MappingProxyType(dict(self.handlers or {}))
        object.__setattr__(self, "handlers", handlers)
        object.__setattr__(
            self,
            "contribution",
            _materialize_contribution(self.declaration, handlers),
        )


@dataclass(frozen=True)
class RegisteredContribution:
    plugin_id: str
    declaration: ContributionDeclaration
    binding: ContributionBinding

    @property
    def kind(self):
        return self.declaration.kind

    @property
    def contribution(self):
        return self.binding.contribution

    @property
    def id(self):
        return self.declaration.descriptor.id


def _split_contribution(kind, contribution):
    expected = CONTRIBUTION_TYPES[kind]
    if not isinstance(contribution, expected):
        raise PluginRegistrationError(
            "{} contributions must be {} objects.".format(
                kind.value,
                expected.__name__,
            )
        )
    handler_names = frozenset(CONTRIBUTION_HANDLER_FIELDS[kind])
    configuration = {}
    handlers = {}
    for declared_field in fields(contribution):
        name = declared_field.name
        value = getattr(contribution, name)
        if name == "descriptor":
            continue
        if name in handler_names:
            if value is not None:
                handlers[name] = value
        else:
            configuration[name] = value
    declaration = ContributionDeclaration(
        kind=kind,
        descriptor=contribution_descriptor(contribution),
        configuration=configuration,
    )
    return declaration, handlers


def _materialize_contribution(declaration, handlers):
    kind = ContributionKind(declaration.kind)
    expected = CONTRIBUTION_TYPES[kind]
    expected_handlers = frozenset(CONTRIBUTION_HANDLER_FIELDS[kind])
    unknown_handlers = set(handlers) - expected_handlers
    if unknown_handlers:
        raise PluginRegistrationError(
            "Unknown {} handlers: {}.".format(
                kind.value,
                ", ".join(sorted(unknown_handlers)),
            )
        )
    if any(not callable(handler) for handler in handlers.values()):
        raise PluginRegistrationError(
            "{} contribution handlers must be callable.".format(kind.value)
        )

    declared_fields = {
        declared_field.name: declared_field
        for declared_field in fields(expected)
    }
    configuration_fields = (
        set(declared_fields) - expected_handlers - {"descriptor"}
    )
    unknown_configuration = (
        set(declaration.configuration) - configuration_fields
    )
    if unknown_configuration:
        raise PluginRegistrationError(
            "Unknown {} declaration fields: {}.".format(
                kind.value,
                ", ".join(sorted(unknown_configuration)),
            )
        )
    required_configuration = {
        name for name in configuration_fields
        if declared_fields[name].default is MISSING
        and declared_fields[name].default_factory is MISSING
    }
    missing_configuration = (
        required_configuration - set(declaration.configuration)
    )
    required_handlers = {
        name for name in expected_handlers
        if declared_fields[name].default is MISSING
        and declared_fields[name].default_factory is MISSING
    }
    missing_handlers = required_handlers - set(handlers)
    if missing_configuration or missing_handlers:
        missing = sorted(missing_configuration | missing_handlers)
        raise PluginRegistrationError(
            "{} declaration requires: {}.".format(
                kind.value,
                ", ".join(missing),
            )
        )
    arguments = {
        "descriptor": declaration.descriptor,
        **dict(declaration.configuration),
        **dict(handlers),
    }
    try:
        return expected(**arguments)
    except (TypeError, ValueError) as error:
        raise PluginRegistrationError(
            "Invalid {} declaration: {}".format(kind.value, error)
        ) from error


class PluginRegistrar:
    """Stage one plugin's contributions before atomically installing them."""

    def __init__(
        self,
        plugin_id,
        capabilities=None,
        declared_capabilities=(),
        unavailable_capabilities=(),
    ):
        self.plugin_id = plugin_id
        self._contributions = []
        self._capabilities = dict(capabilities or {})
        self._declaredCapabilities = frozenset(declared_capabilities)
        self._unavailableCapabilities = frozenset(
            unavailable_capabilities
        )

    def capability(self, name):
        """A service this plugin declared and core granted.

        Refuses anything undeclared rather than returning it, so a plugin
        cannot quietly widen the surface its manifest advertises.
        """
        try:
            return self._capabilities[name]
        except KeyError:
            if name in self._unavailableCapabilities:
                raise PluginScopeError(
                    "Plugin {} declared optional capability {!r}, but the "
                    "current host cannot provide it.".format(
                        self.plugin_id, name
                    )
                ) from None
            if name in self._declaredCapabilities:
                raise PluginScopeError(
                    "Plugin {} declared capability {!r}; it is delivered "
                    "only by its scoped UI context.".format(
                        self.plugin_id, name
                    )
                ) from None
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

    def register_command(self, contribution):
        self._add(ContributionKind.COMMAND, contribution)

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

    def register_native_markup(self, contribution):
        self._add(ContributionKind.NATIVE_MARKUP, contribution)

    def register_transform(self, contribution):
        self._add(ContributionKind.TRANSFORM, contribution)

    def register_conversion_augmentation(self, contribution):
        self._add(ContributionKind.CONVERSION_AUGMENTATION, contribution)

    def register_declaration(self, declaration, handlers):
        """Stage a declaration from any driver with its local proxies."""
        if not isinstance(declaration, ContributionDeclaration):
            raise PluginRegistrationError(
                "Drivers must register ContributionDeclaration objects."
            )
        try:
            # Encoding is validation: only records explicitly present in the
            # API value schema can be declaration data.
            api_value_codec().encode(declaration)
            binding = ContributionBinding(declaration, handlers)
        except (TypeError, ValueError) as error:
            raise PluginRegistrationError(
                "Invalid {} declaration: {}".format(
                    declaration.kind.value,
                    error,
                )
            ) from error
        self._stage(declaration, binding)

    def _add(self, kind, contribution):
        declaration, handlers = _split_contribution(kind, contribution)
        self.register_declaration(declaration, handlers)

    def _stage(self, declaration, binding):
        if any(
            existing.kind in _id_namespace(declaration.kind)
            and existing.id == declaration.descriptor.id
            for existing in self._contributions
        ):
            raise PluginRegistrationError(
                "Plugin {} registered duplicate {} ID {!r}.".format(
                    self.plugin_id,
                    declaration.kind.value,
                    declaration.descriptor.id,
                )
            )
        self._contributions.append(
            RegisteredContribution(
                plugin_id=self.plugin_id,
                declaration=declaration,
                binding=binding,
            )
        )


class PluginRegistry:
    """Own all validated contributions, indexed by capability and stable ID."""

    def __init__(self):
        self._by_kind = defaultdict(dict)
        self._by_plugin = defaultdict(list)

    def registrar(
        self,
        plugin_id,
        capabilities=None,
        declared_capabilities=(),
        unavailable_capabilities=(),
    ):
        return PluginRegistrar(
            plugin_id,
            capabilities=capabilities,
            declared_capabilities=declared_capabilities,
            unavailable_capabilities=unavailable_capabilities,
        )

    def install(self, plugin_id, contributions):
        contributions = tuple(contributions)
        if any(record.plugin_id != plugin_id for record in contributions):
            raise PluginRegistrationError(
                "A plugin cannot install another plugin's contributions."
            )

        collisions = []
        for record in contributions:
            # A plugin's own records are about to be replaced, so only
            # somebody else holding the ID is a conflict: reinstalling a
            # plugin over itself must not refuse the plugin.
            for related_kind in _id_namespace(record.kind):
                owner = self._by_kind[related_kind].get(record.id)
                if owner is not None and owner.plugin_id != plugin_id:
                    collisions.append((related_kind, record.id, owner.plugin_id))
                    break
        if collisions:
            kind, contribution_id, owner = collisions[0]
            raise PluginRegistrationError(
                "{} ID {!r} is already registered by {}.".format(
                    kind.value,
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
    def commands(self):
        return self.contributions(ContributionKind.COMMAND)

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
    def native_markup(self):
        return self.contributions(ContributionKind.NATIVE_MARKUP)

    @property
    def transforms(self):
        return self.contributions(ContributionKind.TRANSFORM)

    @property
    def conversion_augmentations(self):
        return self.contributions(
            ContributionKind.CONVERSION_AUGMENTATION
        )
