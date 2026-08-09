"""Which renderer produces a page, decided by media type alone.

Two things changed here and both matter. Nothing in the search looks up a
plugin, so a second plugin offering the same format becomes selectable by
being installed rather than by anyone coding for it. And nothing producing a
format is a legal state -- a plugin may promise to consume something nothing
provides yet -- so the route reads as unassigned instead of raising.
"""

import pytest

from manuskript.media_types import (
    BBCODE,
    HTML,
    MARKDOWN,
    PLAIN,
    MediaType,
    MediaTypeRegistry,
    core_registry,
)
from manuskript.plugins import (
    ExtensionDescriptor,
    PageExportDocument,
    PageRendererContribution,
    PageTypeContribution,
)
from manuskript.plugins.registry import PluginRegistry
from manuskript.services.media_type_preferences import (
    InMemoryMediaTypePreferences,
)
from manuskript.services.plugin_options import InMemoryPluginOptionStore
from manuskript.ui.plugins.page_types import PageTypeService


PAGE_TYPE = "vendor.page"
FB2 = "application/x-fictionbook+xml"


class Parser:
    def parse(self, source):
        return "PARSED:" + source


class Renderer:
    def render(self, model, target_format, options):
        return PageExportDocument(model, target_format)


class Item:
    def __init__(self, text="a page"):
        self._text = text
        self._properties = {PAGE_TYPE: True}

    def text(self):
        return self._text

    def type(self):
        return "md"

    def ID(self):
        return "1"

    def hasPluginValue(self, key):
        return key in self._properties

    def pluginValue(self, key):
        return self._properties[key]


def renderer(extension_id, formats, priority=0, plugin="vendor.plugin"):
    return plugin, PageRendererContribution(
        ExtensionDescriptor(extension_id, extension_id),
        page_type_id=PAGE_TYPE,
        renderer_factory=Renderer,
        target_formats=tuple(formats),
        priority=priority,
    )


def service(*renderers, media_types=None, option_store=None):
    registry = PluginRegistry()
    by_plugin = {}
    for plugin, contribution in renderers:
        by_plugin.setdefault(plugin, []).append(contribution)
    first = True
    for plugin, contributions in by_plugin.items():
        registrar = registry.registrar(plugin)
        if first:
            registrar.register_page_type(PageTypeContribution(
                ExtensionDescriptor(PAGE_TYPE, "Vendor page"),
                "Vendor page",
                parser_factory=Parser,
            ))
            first = False
        for contribution in contributions:
            registrar.register_page_renderer(contribution)
        registry.install(plugin, registrar.contributions)
    return PageTypeService(
        registry,
        option_store=(
            option_store
            if option_store is not None
            else InMemoryPluginOptionStore()
        ),
        media_types=media_types or core_registry(),
    )


def ids(candidates):
    return [candidate.descriptor.id for candidate in candidates]


# ------------------------------------------------------------ the ordering

def test_an_exact_match_outranks_anything_standing_in():
    subject = service(
        renderer("vendor.stand-in", [MARKDOWN]),
        renderer("vendor.exact", [BBCODE]),
    )

    assert ids(subject.renderers_for(PAGE_TYPE, BBCODE)) == [
        "vendor.exact", "vendor.stand-in",
    ]


def test_priority_decides_between_equally_exact_renderers():
    subject = service(
        renderer("vendor.low", [BBCODE], priority=1),
        renderer("vendor.high", [BBCODE], priority=9),
    )

    assert ids(subject.renderers_for(PAGE_TYPE, BBCODE))[0] == "vendor.high"


def test_the_chain_is_walked_in_order():
    media_types = core_registry()
    media_types.declare(
        MediaType("text/vnd.sv+bbcode", "SV BBCode", base=BBCODE),
        "vendor.sv",
    )
    subject = service(
        renderer("vendor.generic-markdown", [MARKDOWN]),
        renderer("vendor.generic-bbcode", [BBCODE]),
        renderer("vendor.sv", ["text/vnd.sv+bbcode"]),
        media_types=media_types,
    )

    # Its own type, then its declared base, then core's default.
    assert ids(subject.renderers_for(PAGE_TYPE, "text/vnd.sv+bbcode")) == [
        "vendor.sv", "vendor.generic-bbcode", "vendor.generic-markdown",
    ]


def test_a_renderer_appears_once_however_many_steps_match():
    subject = service(renderer("vendor.both", [BBCODE, MARKDOWN]))

    assert ids(subject.renderers_for(PAGE_TYPE, BBCODE)) == ["vendor.both"]


# ------------------------------------------- nothing looks up a plugin

def test_a_second_plugin_offering_the_format_is_a_candidate():
    subject = service(
        renderer("first.bbcode", [BBCODE], plugin="vendor.first"),
        renderer("second.bbcode", [BBCODE], plugin="vendor.second"),
    )

    # Installed by somebody else entirely, and selectable for that reason
    # alone. The page type's owner did not have to know it exists.
    assert ids(subject.renderers_for(PAGE_TYPE, BBCODE)) == [
        "first.bbcode", "second.bbcode",
    ]


# ------------------------------------------------------- unassigned routes

def test_no_producer_resolves_to_nothing_rather_than_raising():
    media_types = core_registry()
    media_types.declare(
        MediaType(FB2, "FictionBook 2", textual=False), "vendor.fb2",
    )
    subject = service(renderer("vendor.markdown", [MARKDOWN]), media_types=media_types)

    # FB2 is not textual, so nothing stands in for it, and nobody produces
    # it. That is a promise waiting on a plugin, not a failure.
    assert subject.renderers_for(PAGE_TYPE, FB2) == ()
    assert subject.resolve_renderer(PAGE_TYPE, FB2) is None


def test_an_unassigned_route_includes_the_page_source_unrendered():
    media_types = core_registry()
    media_types.declare(
        MediaType(FB2, "FictionBook 2", textual=False), "vendor.fb2",
    )
    subject = service(renderer("vendor.markdown", [MARKDOWN]), media_types=media_types)

    document = subject.export_document(Item("raw page source"), FB2)

    assert document == PageExportDocument("raw page source", MARKDOWN)


def test_a_page_type_with_no_renderer_at_all_is_not_an_error():
    subject = service()

    assert subject.resolve_renderer(PAGE_TYPE, BBCODE) is None
    assert subject.export_document(Item("source"), BBCODE) == (
        PageExportDocument("source", MARKDOWN)
    )


# ------------------------------------------------------- the render format

def test_a_stand_in_renderer_is_asked_for_what_it_can_make():
    subject = service(renderer("vendor.markdown-only", [MARKDOWN]))

    _renderer, render_format = subject.resolve_renderer(PAGE_TYPE, HTML)

    # Asked for Markdown, not for the HTML it cannot produce.
    assert render_format == MARKDOWN


def test_an_exact_renderer_is_asked_for_the_target():
    subject = service(renderer("vendor.bbcode", [BBCODE, MARKDOWN]))

    _renderer, render_format = subject.resolve_renderer(PAGE_TYPE, BBCODE)

    assert render_format == BBCODE


# --------------------------------------------------- the default stand-in

def test_markdown_stands_in_for_textual_formats_by_default():
    registry = core_registry()

    assert registry.fallback_chain(HTML) == (HTML, MARKDOWN)
    assert registry.fallback_chain(PLAIN) == (PLAIN, MARKDOWN)
    assert registry.fallback_chain(MARKDOWN) == (MARKDOWN,)


def test_nothing_stands_in_for_a_binary_destination():
    registry = core_registry()

    # ePub is reached through a representation; it is not one.
    assert registry.fallback_chain("application/epub+zip") == (
        "application/epub+zip",
    )


def test_a_format_declared_but_not_yet_named_gets_no_stand_in():
    registry = core_registry()
    # Bare interest: somebody knows the name, nobody has said what it is.
    registry.declare(FB2, "vendor.reader")

    assert registry.fallback_chain(FB2) == (FB2,)

    registry.declare(MediaType(FB2, "FictionBook 2"), "vendor.fb2")

    # Named as textual, so now Markdown may stand in for it.
    assert registry.fallback_chain(FB2) == (FB2, MARKDOWN)


def test_a_registry_with_no_default_leaves_formats_alone():
    registry = MediaTypeRegistry()
    registry.declare(MediaType(HTML, "HTML"), "core")

    assert registry.fallback_chain(HTML) == (HTML,)


def test_a_user_assignment_outranks_the_default():
    registry = core_registry()
    registry.assign_fallback(HTML, PLAIN)

    assert registry.fallback_chain(HTML) == (HTML, PLAIN, MARKDOWN)


def test_a_corrupted_fallback_loop_does_not_stop_an_export():
    registry = core_registry()
    # What a hand-edited preferences file could describe.
    registry._fallbacks[HTML] = BBCODE
    registry._fallbacks[BBCODE] = HTML
    subject = service(renderer("vendor.html", [HTML]), media_types=registry)

    # Reported, then the exact type is used alone rather than refusing.
    assert subject.fallback_chain(HTML) == (HTML,)
    assert ids(subject.renderers_for(PAGE_TYPE, HTML)) == ["vendor.html"]


# ------------------------------------------------------------- persistence

def test_a_remembered_fallback_is_applied_to_a_registry():
    preferences = InMemoryMediaTypePreferences()
    preferences.remember_fallback(HTML, PLAIN)

    registry = preferences.apply(core_registry())

    assert registry.fallback(HTML) == PLAIN
    assert registry.fallback_chain(HTML) == (HTML, PLAIN, MARKDOWN)


def test_forgetting_a_fallback_returns_to_the_default():
    preferences = InMemoryMediaTypePreferences()
    preferences.remember_fallback(HTML, PLAIN)
    preferences.remember_fallback(HTML, "")

    registry = preferences.apply(core_registry())

    assert registry.fallback(HTML) == ""
    assert registry.fallback_chain(HTML) == (HTML, MARKDOWN)


def test_a_stored_fallback_naming_a_vanished_format_is_dropped():
    preferences = InMemoryMediaTypePreferences({HTML: FB2})

    registry = preferences.apply(core_registry())

    # The plugin that declared FB2 was uninstalled. Manuskript still starts.
    assert registry.fallback(HTML) == ""
    assert registry.fallback_chain(HTML) == (HTML, MARKDOWN)


def test_a_stored_fallback_that_would_loop_is_dropped():
    preferences = InMemoryMediaTypePreferences({MARKDOWN: HTML})

    registry = preferences.apply(core_registry())

    # HTML already falls back to Markdown by default, so this closes a
    # loop. Refused on load rather than allowed to hang an export.
    assert registry.fallback(MARKDOWN) == ""
