"""The routing panel is core's to build and the plugin's to place.

Every plugin with a page type needs this widget, so core owns it and its
faults are fixed once. But core never puts it anywhere: the details pane
belongs to the selected plugin, and drawing there uninvited is what leaked
one plugin's routing into another's panel. A plugin asks, or gets nothing.
"""

import pytest

from manuskript.exporter.page_routes import (
    PageRendererRoute,
    page_renderer_route_id,
)
from manuskript.media_types import BBCODE, MARKDOWN, PLAIN, core_registry
from manuskript.plugins import (
    ExtensionDescriptor,
    OptionField,
    PageRendererContribution,
    PageTypeContribution,
)
from manuskript.plugins.capabilities import (
    CAPABILITY_MEDIA_REGISTRY,
    CAPABILITY_UI_EXPORT_ROUTING,
    capability_catalogue,
    grant,
)
from manuskript.plugins.errors import PluginScopeError
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.plugin_options import InMemoryPluginOptionStore
from manuskript.ui.plugins.page_routing import PageRoutingGateway
from manuskript.ui.plugins.page_types import PageTypeService
from manuskript.ui.plugins.routing_panel import (
    AUTOMATIC,
    ExportRoutingPanel,
    ExportRoutingService,
)


PAGE_TYPE = "vendor.page"
OWNER = "vendor.plugin"

BBCODE_ROUTE = PageRendererRoute(
    page_renderer_route_id(BBCODE, BBCODE),
    "BBCode", BBCODE, BBCODE, "Manuskript",
)
PLAIN_ROUTE = PageRendererRoute(
    page_renderer_route_id(PLAIN, MARKDOWN),
    "Plain text", PLAIN, MARKDOWN, "Manuskript",
)
FB2 = "application/x-fictionbook+xml"


def renderer(extension_id, formats, options=(), priority=0):
    return PageRendererContribution(
        ExtensionDescriptor(extension_id, extension_id),
        page_type_id=PAGE_TYPE,
        renderer_factory=object,
        target_formats=tuple(formats),
        options=tuple(options),
        priority=priority,
    )


def build(routes, *renderers, store=None, media_types=None,
          owners=None):
    registry = PluginRegistry()
    owners = owners or {}
    grouped = {}
    for contribution in renderers:
        plugin = owners.get(contribution.descriptor.id, OWNER)
        grouped.setdefault(plugin, []).append(contribution)
    first = True
    for plugin, contributions in grouped.items():
        registrar = registry.registrar(plugin)
        if first:
            registrar.register_page_type(PageTypeContribution(
                ExtensionDescriptor(PAGE_TYPE, "Vendor page"),
                "Vendor page",
                parser_factory=object,
            ))
            first = False
        for contribution in contributions:
            registrar.register_page_renderer(contribution)
        registry.install(plugin, registrar.contributions)
    if not renderers:
        registrar = registry.registrar(OWNER)
        registrar.register_page_type(PageTypeContribution(
            ExtensionDescriptor(PAGE_TYPE, "Vendor page"),
            "Vendor page",
            parser_factory=object,
        ))
        registry.install(OWNER, registrar.contributions)
    service = PageTypeService(
        registry,
        option_store=store or InMemoryPluginOptionStore(),
        media_types=media_types or core_registry(),
    )
    gateway = PageRoutingGateway(
        OWNER, registry, service, lambda: routes,
    )
    return gateway


def panel(gateway):
    return ExportRoutingPanel(gateway, PAGE_TYPE)


def items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


# ------------------------------------------------- state 1: exact choices

def test_a_destination_with_one_renderer_gets_no_row():
    gateway = build((BBCODE_ROUTE,), renderer("vendor.bb", [BBCODE]))

    subject = panel(gateway)

    # Nothing to pick, so nothing that looks pickable. The earlier version
    # gave every destination a dropdown, and with one renderer that meant
    # listing "Automatic - vendor.bb" above "vendor.bb".
    assert subject._combos == {}
    assert subject.form.rowCount() == 0
    assert subject.noticeLabel.text() == "vendor.bb: BBCode"


def test_destinations_settled_by_one_renderer_are_listed_together():
    gateway = build(
        (BBCODE_ROUTE, PLAIN_ROUTE),
        renderer("vendor.md", [MARKDOWN]),
    )

    subject = panel(gateway)

    # One line naming the renderer once, rather than a row per destination
    # repeating it. Ten rows of one name implied ten decisions.
    assert subject._combos == {}
    assert subject.noticeLabel.text() == "vendor.md: BBCode, Plain text"


def test_a_choice_between_renderers_leads_with_automatic():
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE], priority=9),
        renderer("vendor.other", [BBCODE]),
    )

    combo = panel(gateway)._combos[BBCODE_ROUTE.id]

    # Now there is a decision, so Automatic leads and says what it
    # resolves to -- and never displays a renderer as though somebody had
    # picked it, which is what the old panel did.
    assert items(combo) == [
        "Automatic — vendor.bb", "vendor.bb", "vendor.other",
    ]
    assert combo.currentData() == AUTOMATIC


def test_automatic_never_carries_the_stand_in_note():
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.md", [MARKDOWN], priority=9),
        renderer("vendor.other", [MARKDOWN]),
    )

    combo = panel(gateway)._combos[BBCODE_ROUTE.id]

    # "Automatic — vendor.md — as Markdown" was three clauses and two
    # dashes for one fact about one renderer.
    assert combo.itemText(0) == "Automatic — vendor.md"
    assert "as Markdown" in combo.itemText(1)


def test_a_saved_choice_is_shown_as_chosen():
    store = InMemoryPluginOptionStore()
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE]),
        renderer("vendor.other", [BBCODE]),
        store=store,
    )
    gateway.select(
        PAGE_TYPE, BBCODE_ROUTE.id, "vendor.other",
        representation_format=BBCODE,
    )

    combo = panel(gateway)._combos[BBCODE_ROUTE.id]

    assert combo.currentData() == "vendor.other"


def test_a_pin_stays_clearable_even_as_the_only_renderer():
    store = InMemoryPluginOptionStore()
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE]),
        store=store,
    )
    gateway.select(
        PAGE_TYPE, BBCODE_ROUTE.id, "vendor.bb",
        representation_format=BBCODE,
    )
    subject = panel(gateway)
    combo = subject._combos[BBCODE_ROUTE.id]

    # A sole renderer is normally shown alone, but an existing pin has to
    # stay offered or there would be no way left to undo it.
    assert combo.findData(AUTOMATIC) >= 0
    assert combo.currentData() == "vendor.bb"

    combo.setCurrentIndex(combo.findData(AUTOMATIC))

    assert gateway.selected(PAGE_TYPE, BBCODE_ROUTE.id) == ""
    assert store.load_values(
        PageTypeService.SELECTION_PREFIX + PAGE_TYPE
    ) == {}


def test_another_plugins_renderer_is_attributed():
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE]),
        renderer("stranger.bb", [BBCODE]),
        owners={"stranger.bb": "other.plugin"},
    )

    labels = "".join(items(panel(gateway)._combos[BBCODE_ROUTE.id]))

    assert "other.plugin" in labels
    # Its own renderer is not annotated with its own name.
    assert labels.count("vendor.plugin") == 0


# --------------------------------------------- state 2: only a stand-in

def test_a_stand_in_is_explained_where_it_is_a_choice():
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE], priority=9),
        renderer("vendor.md", [MARKDOWN]),
    )

    labels = items(panel(gateway)._combos[BBCODE_ROUTE.id])

    # Here the two options really differ in what comes out, so the one
    # that cannot make BBCode says so. This is the only place that note
    # earns its keep -- on a settled destination it described a
    # distinction with no consequence.
    assert "vendor.bb" in labels
    assert any("as Markdown" in label for label in labels)


# --------------------------------------------------- state 3: unassigned

def unassigned_route():
    return PageRendererRoute(
        page_renderer_route_id(FB2, FB2), "FictionBook", FB2, FB2, "Vendor",
    )


def test_a_route_nothing_can_produce_reads_as_unassigned():
    media_types = core_registry()
    media_types.declare(FB2, "vendor.fb2")
    gateway = build(
        (unassigned_route(),),
        renderer("vendor.md", [MARKDOWN]),
        media_types=media_types,
    )

    subject = panel(gateway)

    assert subject._combos == {}
    field = subject.form.itemAt(0, subject.form.FieldRole).widget()
    assert field.text() == "Unassigned"
    assert field.isEnabled() is False


def test_an_unassigned_route_names_what_was_searched():
    media_types = core_registry()
    media_types.declare(FB2, "vendor.fb2")
    gateway = build(
        (unassigned_route(),),
        renderer("vendor.md", [MARKDOWN]),
        media_types=media_types,
    )

    subject = panel(gateway)
    field = subject.form.itemAt(0, subject.form.FieldRole).widget()

    # Inert, but not silent: it says which formats had no producer.
    assert FB2 in field.toolTip()


def test_no_routes_at_all_says_so():
    gateway = build((), renderer("vendor.bb", [BBCODE]))

    subject = panel(gateway)

    assert subject._combos == {}
    assert "No export format" in subject.noticeLabel.text()


# ------------------------------------------------------- configure buttons

def test_only_the_plugins_own_renderers_get_a_configure_button():
    gateway = build(
        (BBCODE_ROUTE,),
        renderer("vendor.bb", [BBCODE], options=(
            OptionField("depth", "Depth", default=1),
        )),
        renderer("stranger.bb", [BBCODE], options=(
            OptionField("depth", "Depth", default=1),
        )),
        owners={"stranger.bb": "other.plugin"},
    )

    subject = panel(gateway)
    labels = [
        subject.optionsRow.itemAt(i).widget().text()
        for i in range(subject.optionsRow.count())
        if subject.optionsRow.itemAt(i).widget() is not None
    ]

    assert any("vendor.bb" in label for label in labels)
    assert not any("stranger.bb" in label for label in labels)


# ------------------------------------------------------ the negotiation

def test_the_service_refuses_a_page_type_the_plugin_does_not_own():
    gateway = build((BBCODE_ROUTE,), renderer("vendor.bb", [BBCODE]))
    service = ExportRoutingService(gateway)

    with pytest.raises(PluginScopeError):
        service.panel("someone.else-page")


def test_the_service_lists_the_plugins_own_page_types():
    gateway = build((BBCODE_ROUTE,), renderer("vendor.bb", [BBCODE]))
    service = ExportRoutingService(gateway)

    assert [
        contribution.descriptor.id
        for contribution in service.page_types
    ] == [PAGE_TYPE]


def test_a_ui_capability_is_catalogued_but_not_built_at_load():
    catalogue = capability_catalogue()

    for name in (CAPABILITY_UI_EXPORT_ROUTING, CAPABILITY_MEDIA_REGISTRY):
        assert catalogue[name].deferred is True

    granted, missing = grant([CAPABILITY_UI_EXPORT_ROUTING])

    # The name gates at load -- a plugin requiring one core lacks is still
    # refused before its code runs -- but there is no application yet and
    # no plugin to scope it to, so nothing is handed over.
    assert missing == ()
    assert granted == {}


def test_requiring_a_capability_core_lacks_still_reports_it():
    _granted, missing = grant(["ui.telepathy"])

    assert missing == ("ui.telepathy",)
