import pytest

from manuskript.plugins.api import (
    EditorWorkspaceContribution,
    ExportContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.registry import PluginRegistry


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
