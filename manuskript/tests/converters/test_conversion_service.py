"""Converting markup, with whatever plugins have added, for a caller that
does not know they exist.

That last part is the point. A plugin owning its own source format has to
convert that format itself -- nobody else can -- but the hop from Markdown to
HTML is not its business, and when it performed that hop itself it silently
opted out of every addition other plugins had made. The list somebody had
taught Markdown about came out as a paragraph in one renderer and a list in
another.

No format is named in the service's interface: a route is two media types
supplied by the caller. So the tests name them, the way the code performing a
conversion does.
"""

import sys

import pytest

from manuskript.converters.conversion_service import (
    ConversionService,
    UnknownRoute,
    conversion_service,
    core_engines,
)
from manuskript.media_types import BBCODE, HTML, MARKDOWN
from manuskript.plugins.api import (
    ConversionAugmentationContribution,
    ExtensionDescriptor,
)
from manuskript.plugins.capabilities import (
    CAPABILITY_CONVERSION,
    PluginCapabilityContext,
    grant,
)
from manuskript.plugins.registry import PluginRegistry

markdown_module = pytest.importorskip("markdown")


class Shouting(markdown_module.Extension):
    """An addition with an unmistakable effect, so it cannot be mistaken for
    something Markdown does by itself.
    """

    def extendMarkdown(self, md):
        md.preprocessors.register(_Shout(md), "shouting", 30)


class _Shout(markdown_module.preprocessors.Preprocessor):
    def run(self, lines):
        return [line.upper() for line in lines]


def an_augmentation(source=MARKDOWN, target=HTML, factory=Shouting):
    return ConversionAugmentationContribution(
        descriptor=ExtensionDescriptor(id="vendor.shout", name="Shouting"),
        source_format=source,
        target_format=target,
        augmentation_factory=factory,
    )


def registry_with(*contributions):
    registry = PluginRegistry()
    if contributions:
        registrar = registry.registrar("vendor.markup")
        for contribution in contributions:
            registrar.register_conversion_augmentation(contribution)
        registry.install("vendor.markup", registrar.contributions)
    return registry


# ------------------------------------------------------------- the routes

def test_it_converts_the_routes_core_performs():
    service = conversion_service()

    assert service.can_convert(MARKDOWN, HTML)
    assert service.can_convert(MARKDOWN, BBCODE)
    assert "<em>" in service.convert("*yes*", MARKDOWN, HTML)
    assert "[i]" in service.convert("*yes*", MARKDOWN, BBCODE)


def test_a_route_it_cannot_perform_says_so():
    """Rather than returning the text unconverted, which would look like a
    conversion that did nothing.
    """
    service = conversion_service()

    assert not service.can_convert(HTML, MARKDOWN)
    with pytest.raises(UnknownRoute, match="text/html"):
        service.convert("<p>x</p>", HTML, MARKDOWN)


def test_a_route_whose_library_is_not_installed_is_not_offered():
    """python-markdown is a listed requirement, but an installation can be
    without it and core guards for that in its own HTML exporter. A caller
    told the route exists and then handed an ImportError has nothing left to
    do; one told the route does not exist can show the text plainly instead.
    """
    with pytest.MonkeyPatch().context() as without_markdown:
        without_markdown.setitem(sys.modules, "markdown", None)
        engines = core_engines()
        service = ConversionService(engines)

    assert (MARKDOWN, HTML) not in engines
    assert (MARKDOWN, BBCODE) in engines
    assert not service.can_convert(MARKDOWN, HTML)
    with pytest.raises(UnknownRoute):
        service.convert("*yes*", MARKDOWN, HTML)


def test_empty_text_is_returned_as_it_came():
    service = conversion_service()

    assert service.convert("", MARKDOWN, HTML) == ""
    assert service.convert(None, MARKDOWN, HTML) is None


# ------------------------------------------------- what plugins have added

def test_a_caller_gets_additions_it_never_asked_about():
    """The whole reason the service exists. This caller names two formats and
    receives someone else's addition, without knowing it was made.
    """
    service = conversion_service(registry=registry_with(an_augmentation()))

    html = service.convert("quiet", MARKDOWN, HTML)

    assert "QUIET" in html


def test_an_addition_for_another_route_stays_out_of_this_one():
    service = conversion_service(
        registry=registry_with(an_augmentation(target=BBCODE)),
    )

    assert "QUIET" not in service.convert("quiet", MARKDOWN, HTML)


def test_additions_arrive_in_the_shape_that_route_takes():
    """A markdown.Extension for Markdown to HTML, a rule for Markdown to
    BBCode: what an addition must be belongs to the route, which is why the
    service takes engines rather than assuming one shape.
    """
    engines = core_engines()

    assert set(engines) == {(MARKDOWN, HTML), (MARKDOWN, BBCODE)}
    assert all(callable(engine) for engine in engines.values())


def test_a_plugin_enabled_later_still_contributes():
    """The service holds the registry, not a snapshot of it. Somebody
    enabling a plugin expects the next rendering to show it.
    """
    registry = registry_with()
    service = conversion_service(registry=registry)

    assert "QUIET" not in service.convert("quiet", MARKDOWN, HTML)

    registrar = registry.registrar("vendor.markup")
    registrar.register_conversion_augmentation(an_augmentation())
    registry.install("vendor.markup", registrar.contributions)

    assert "QUIET" in service.convert("quiet", MARKDOWN, HTML)


def test_an_addition_that_will_not_build_does_not_stop_the_conversion():
    def broken():
        raise RuntimeError("no addition today")

    said = []
    service = conversion_service(
        registry=registry_with(an_augmentation(factory=broken)),
        report_error=said.append,
    )

    assert "<em>" in service.convert("*yes*", MARKDOWN, HTML)
    assert said


# --------------------------------------------------------- as a capability

def test_a_plugin_asks_for_it_by_name_and_receives_a_service():
    registry = registry_with(an_augmentation())
    context = PluginCapabilityContext(
        registry=registry,
        conversion_service=lambda: conversion_service(registry=registry),
    )

    granted, missing = grant([CAPABILITY_CONVERSION], context)

    assert missing == ()
    assert "QUIET" in granted[CAPABILITY_CONVERSION].convert(
        "quiet", MARKDOWN, HTML,
    )


def test_without_a_context_the_capability_is_refused_not_half_built():
    """A plugin asking for a service core cannot assemble is told so before
    any of its code runs, which is what every other unmet requirement does.
    """
    granted, missing = grant([CAPABILITY_CONVERSION])

    assert granted == {}
    assert missing == (CAPABILITY_CONVERSION,)


def test_a_service_with_no_registry_still_converts():
    """Conversion is core's, and works with no plugin layer at all."""
    service = ConversionService(core_engines())

    assert "<em>" in service.convert("*yes*", MARKDOWN, HTML)
