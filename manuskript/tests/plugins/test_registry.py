import pytest
import json

from manuskript.plugins.api import (
    ContributionDeclaration,
    EditorWorkspaceContribution,
    ExportContribution,
    ExtensionDescriptor,
    MarkupContribution,
    MarkupMode,
    NativeMarkupContribution,
)
from manuskript.plugins.contracts import ContributionKind
from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.registry import PluginRegistry
from manuskript.plugins.values import api_value_codec


def exporter(extension_id):
    return ExportContribution(
        descriptor=ExtensionDescriptor(
            id=extension_id,
            name=extension_id,
        ),
        engine_factory=object,
    )


def workspace(extension_id):
    return EditorWorkspaceContribution(
        descriptor=ExtensionDescriptor(
            id=extension_id,
            name=extension_id,
        ),
        workspace_factory=lambda context, parent: object(),
        minimum_selection=2,
    )


def test_registry_installs_one_plugin_atomically():
    registry = PluginRegistry()
    registrar = registry.registrar("example.first")
    registrar.register_exporter(exporter("example.fb2"))

    registry.install(
        "example.first",
        registrar.contributions,
    )

    assert registry.exporters == (
        registrar.contributions[0].contribution,
    )


def test_registry_separates_portable_declaration_from_local_handlers():
    registry = PluginRegistry()
    registrar = registry.registrar("example.first")
    contribution = exporter("example.fb2")

    registrar.register_exporter(contribution)
    record = registrar.contributions[0]
    wire = api_value_codec().encode(record.declaration)

    assert record.declaration.kind is ContributionKind.EXPORTER
    assert record.declaration.configuration["output_format"] == "example.fb2"
    assert "engine_factory" not in record.declaration.configuration
    assert record.binding.handlers["engine_factory"] is object
    assert record.contribution.engine_factory is object
    assert "engine_factory" not in json.dumps(wire)


def test_driver_can_register_a_declaration_with_proxy_handlers():
    registrar = PluginRegistry().registrar("example.remote")
    declaration = ContributionDeclaration(
        ContributionKind.EXPORTER,
        ExtensionDescriptor("example.remote.export", "Remote"),
        {"options": (), "output_format": "text/example"},
    )

    registrar.register_declaration(
        declaration,
        {"engine_factory": object},
    )

    contribution = registrar.contributions[0].contribution
    assert contribution.descriptor == declaration.descriptor
    assert contribution.output_format == "text/example"
    assert contribution.engine_factory is object


def test_declaration_requires_the_handlers_its_kind_promises():
    registrar = PluginRegistry().registrar("example.remote")
    declaration = ContributionDeclaration(
        ContributionKind.EXPORTER,
        ExtensionDescriptor("example.remote.export", "Remote"),
        {"options": (), "output_format": "text/example"},
    )

    with pytest.raises(PluginRegistrationError, match="engine_factory"):
        registrar.register_declaration(declaration, {})


def test_declaration_rejects_unknown_or_nonportable_configuration():
    registrar = PluginRegistry().registrar("example.remote")
    descriptor = ExtensionDescriptor("example.remote.export", "Remote")
    unknown = ContributionDeclaration(
        ContributionKind.EXPORTER,
        descriptor,
        {"options": (), "output_format": "text/example", "surprise": 1},
    )
    nonportable = ContributionDeclaration(
        ContributionKind.EXPORTER,
        descriptor,
        {"options": (), "output_format": object()},
    )

    with pytest.raises(PluginRegistrationError, match="Unknown.*fields"):
        registrar.register_declaration(unknown, {"engine_factory": object})
    with pytest.raises(PluginRegistrationError, match="portable"):
        registrar.register_declaration(
            nonportable,
            {"engine_factory": object},
        )


def test_registry_rejects_cross_plugin_ids_without_partial_install():
    registry = PluginRegistry()
    first = registry.registrar("example.first")
    first.register_exporter(exporter("example.fb2"))
    registry.install("example.first", first.contributions)
    second = registry.registrar("example.second")
    second.register_exporter(exporter("example.mobi"))
    second.register_exporter(exporter("example.fb2"))

    with pytest.raises(
        PluginRegistrationError,
        match="already registered",
    ):
        registry.install("example.second", second.contributions)

    assert [
        contribution.descriptor.id
        for contribution in registry.exporters
    ] == ["example.fb2"]


def test_portable_and_native_markup_share_one_routing_id_namespace():
    registry = PluginRegistry()
    first = registry.registrar("example.first")
    first.register_markup(MarkupContribution(
        ExtensionDescriptor("example.markup", "Portable markup"),
        MarkupMode.REPLACE,
        analyze=lambda request: None,
    ))
    registry.install("example.first", first.contributions)
    second = registry.registrar("example.second")
    second.register_native_markup(NativeMarkupContribution(
        ExtensionDescriptor("example.markup", "Native markup"),
        MarkupMode.REPLACE,
        highlighter_factory=lambda editor: None,
    ))

    with pytest.raises(PluginRegistrationError, match="already registered"):
        registry.install("example.second", second.contributions)

    assert len(registry.markup) == 1
    assert registry.native_markup == ()


def test_a_plugin_may_reinstall_over_its_own_contributions():
    """Reinstalling replaces a plugin's records, so its own IDs are not
    conflicts -- only somebody else already holding one is.
    """
    registry = PluginRegistry()
    first = registry.registrar("example.first")
    first.register_exporter(exporter("example.fb2"))
    registry.install("example.first", first.contributions)

    again = registry.registrar("example.first")
    again.register_exporter(exporter("example.fb2"))
    registry.install("example.first", again.contributions)

    assert [
        contribution.descriptor.id
        for contribution in registry.exporters
    ] == ["example.fb2"]


@pytest.mark.parametrize("bad_id", [
    "flat",              # no namespace at all
    "dotted.but bad",    # whitespace
    ".leading",          # boundary characters must be alphanumeric
    "trailing.",
    "sneaky:colon.name",
])
def test_extension_ids_must_be_dotted_names(bad_id):
    """Extension IDs are addressed globally -- by routing selections, by
    other plugins -- so they carry their namespace with them.
    """
    with pytest.raises(ValueError, match="Invalid extension ID"):
        ExtensionDescriptor(id=bad_id, name="Bad")


def test_registry_exposes_editor_workspaces_by_capability():
    registry = PluginRegistry()
    registrar = registry.registrar("example.comparison")
    contribution = workspace("example.variants")
    registrar.register_editor_workspace(contribution)

    registry.install("example.comparison", registrar.contributions)

    assert registry.editor_workspaces == (contribution,)
    assert registry.records("editor_workspace")[0].plugin_id == (
        "example.comparison"
    )


def test_editor_workspace_validates_selection_bounds():
    with pytest.raises(ValueError, match="maximum_selection"):
        EditorWorkspaceContribution(
            descriptor=ExtensionDescriptor(
                id="invalid.workspace",
                name="Invalid",
            ),
            workspace_factory=lambda context, parent: object(),
            minimum_selection=2,
            maximum_selection=1,
        )
