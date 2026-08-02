"""The plugin details pane belongs to the selected plugin, and only to it."""

import pytest
from PyQt5.QtCore import Qt

from manuskript.exporter.page_routes import PageRendererRoute
from manuskript.plugins.api import PluginSettingsContext
from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins.runtime import PluginRuntime
from manuskript.services.plugin_options import InMemoryPluginOptionStore
from manuskript.services.plugin_preferences import (
    InMemoryPluginPreferences,
)
from manuskript.tests.plugins.test_runtime import create_plugin
from manuskript.ui.plugins.manager import PluginManagerDialog
from manuskript.ui.plugins.page_routing import PageRoutingGateway
from manuskript.ui.plugins.page_types import PageTypeService


PAGES_SOURCE = """
from PyQt5.QtWidgets import QLabel

from manuskript.plugins import (
    ExtensionDescriptor, PageRendererContribution, PageTypeContribution,
    PluginSettingsContribution)


def register(api):
    api.register_page_type(PageTypeContribution(
        descriptor=ExtensionDescriptor(id='pages.type', name='Fancy page'),
        property_label='Fancy page',
        parser_factory=object,
    ))
    api.register_page_renderer(PageRendererContribution(
        descriptor=ExtensionDescriptor(
            id='pages.renderer', name='Fancy renderer'),
        page_type_id='pages.type',
        renderer_factory=object,
        target_formats=('markdown',),
    ))
    api.register_settings_panel(PluginSettingsContribution(
        descriptor=ExtensionDescriptor(
            id='pages.settings', name='Fancy settings'),
        widget_factory=lambda context, parent=None: QLabel(
            'FANCY-PANEL-MARKER', parent),
    ))
"""

WORKSPACE_SOURCE = """
from manuskript.plugins import (
    EditorWorkspaceContribution, ExtensionDescriptor)


def register(api):
    api.register_editor_workspace(EditorWorkspaceContribution(
        descriptor=ExtensionDescriptor(
            id='spaces.workspace', name='Side by side'),
        workspace_factory=lambda context, parent=None: None,
    ))
"""

FOREIGN_RENDERER_SOURCE = """
from manuskript.plugins import (
    ExtensionDescriptor, PageRendererContribution)


def register(api):
    api.register_page_renderer(PageRendererContribution(
        descriptor=ExtensionDescriptor(
            id='other.renderer', name='Borrowed renderer'),
        page_type_id='pages.type',
        renderer_factory=object,
        target_formats=('markdown',),
        priority=5,
    ))
"""

BROKEN_PANEL_SOURCE = """
from manuskript.plugins import ExtensionDescriptor, PluginSettingsContribution


def _explode(context, parent=None):
    raise RuntimeError('panel is broken')


def register(api):
    api.register_settings_panel(PluginSettingsContribution(
        descriptor=ExtensionDescriptor(id='bad.settings', name='Bad'),
        widget_factory=_explode,
    ))
"""

ROUTES = (
    PageRendererRoute(
        "plain:markdown", "Plain text", "plain", "markdown", "Manuskript",
    ),
)


def build_runtime(tmp_path, *sources):
    ids = []
    for index, source in enumerate(sources):
        plugin_id = "plugin.{}".format(index)
        ids.append(plugin_id)
        create_plugin(tmp_path, plugin_id=plugin_id, source=source)
    runtime = PluginRuntime([tmp_path], InMemoryPluginPreferences(ids))
    runtime.discover()
    runtime.load_enabled()
    return runtime


def build_dialog(runtime, routes=ROUTES):
    store = InMemoryPluginOptionStore()
    page_types = PageTypeService(runtime.registry, store)

    def context(plugin_id):
        return PluginSettingsContext(
            plugin_id=plugin_id,
            page_routing=PageRoutingGateway(
                plugin_id,
                runtime.registry,
                page_types,
                export_routes_provider=lambda: routes,
            ),
            option_store=store,
            edit_options=lambda *a, **k: None,
            show_status=lambda *a, **k: None,
        )

    return PluginManagerDialog(
        runtime,
        option_store=store,
        settings_context_provider=context,
    )


def select(dialog, plugin_id):
    for index in range(dialog.pluginList.topLevelItemCount()):
        item = dialog.pluginList.topLevelItem(index)
        if item.data(0, Qt.UserRole) == plugin_id:
            dialog.pluginList.setCurrentItem(item)
            return
    raise AssertionError("no row for " + plugin_id)


def panel_text(dialog):
    widget = dialog.pluginPanels.get(dialog.selected_plugin_id())
    if widget is None or not widget.isVisible():
        return ""
    return " ".join(
        child.text()
        for child in widget.findChildren(type(dialog.nameLabel))
    )


def test_plugin_without_a_panel_gets_empty_space(tmp_path):
    runtime = build_runtime(tmp_path, PAGES_SOURCE, WORKSPACE_SOURCE)
    dialog = build_dialog(runtime)
    dialog.show()

    select(dialog, "plugin.1")

    assert dialog.pluginPanels.get("plugin.1") is None
    assert not dialog.pluginSpace.isVisible()


def test_one_plugins_panel_never_shows_under_another(tmp_path):
    runtime = build_runtime(tmp_path, PAGES_SOURCE, WORKSPACE_SOURCE)
    dialog = build_dialog(runtime)
    dialog.show()

    select(dialog, "plugin.0")
    assert "FANCY-PANEL-MARKER" in panel_text(dialog)

    select(dialog, "plugin.1")
    assert panel_text(dialog) == ""
    assert not dialog.pluginPanels["plugin.0"].isVisible()

    select(dialog, "plugin.0")
    assert "FANCY-PANEL-MARKER" in panel_text(dialog)


def test_a_broken_panel_does_not_break_the_manager(tmp_path):
    runtime = build_runtime(tmp_path, BROKEN_PANEL_SOURCE)
    dialog = build_dialog(runtime)
    dialog.show()

    assert dialog.pluginSpace.isVisible()
    assert "panel is broken" in panel_text(dialog)
    assert dialog.nameLabel.text()


def test_disabling_a_plugin_discards_its_panel(tmp_path):
    runtime = build_runtime(tmp_path, PAGES_SOURCE)
    dialog = build_dialog(runtime)
    dialog.show()
    assert dialog.pluginPanels.get("plugin.0") is not None

    dialog.disable_selected()

    assert dialog.pluginPanels.get("plugin.0") is None
    assert not dialog.pluginSpace.isVisible()


def test_gateway_exposes_only_the_plugins_own_page_types(tmp_path):
    runtime = build_runtime(tmp_path, PAGES_SOURCE, WORKSPACE_SOURCE)
    store = InMemoryPluginOptionStore()
    page_types = PageTypeService(runtime.registry, store)

    owner = PageRoutingGateway(
        "plugin.0", runtime.registry, page_types, lambda: ROUTES)
    stranger = PageRoutingGateway(
        "plugin.1", runtime.registry, page_types, lambda: ROUTES)

    assert [c.descriptor.id for c in owner.page_types] == ["pages.type"]
    assert stranger.page_types == ()
    assert owner.owns("pages.type")
    assert not stranger.owns("pages.type")


def test_gateway_refuses_a_page_type_the_plugin_does_not_own(tmp_path):
    runtime = build_runtime(tmp_path, PAGES_SOURCE, WORKSPACE_SOURCE)
    store = InMemoryPluginOptionStore()
    page_types = PageTypeService(runtime.registry, store)
    stranger = PageRoutingGateway(
        "plugin.1", runtime.registry, page_types, lambda: ROUTES)

    with pytest.raises(PluginScopeError):
        stranger.candidates("pages.type", "markdown")
    with pytest.raises(PluginScopeError):
        stranger.selected("pages.type", "plain:markdown")
    with pytest.raises(PluginScopeError):
        stranger.select(
            "pages.type", "plain:markdown", "pages.renderer",
            representation_format="markdown",
        )

    assert store.load_values(
        PageTypeService.SELECTION_PREFIX + "pages.type"
    ) == {}


def test_gateway_offers_another_plugins_renderer_for_its_own_page_type(
        tmp_path):
    runtime = build_runtime(
        tmp_path, PAGES_SOURCE, FOREIGN_RENDERER_SOURCE)
    store = InMemoryPluginOptionStore()
    page_types = PageTypeService(runtime.registry, store)
    gateway = PageRoutingGateway(
        "plugin.0", runtime.registry, page_types, lambda: ROUTES)

    candidates = gateway.candidates("pages.type", "markdown")
    ids = [renderer.descriptor.id for renderer in candidates]

    # Routing spans plugins: plugin.1's renderer is a legitimate choice
    # for plugin.0's page type, and is attributed to its real owner.
    assert set(ids) == {"pages.renderer", "other.renderer"}
    assert gateway.owner_of("other.renderer") == "plugin.1"
    assert gateway.owner_of("pages.renderer") == "plugin.0"

    gateway.select(
        "pages.type", "plain:markdown", "other.renderer",
        representation_format="markdown",
    )

    assert gateway.selected("pages.type", "plain:markdown") == (
        "other.renderer"
    )
