"""Middleware over a format somebody else produces.

A transform takes content in one media type and returns it in the same one:
a table-of-contents injector, a link rewriter, a house-style pass. It is not
a converter, because it converts nothing, and it is not a producer either --
it waits for something that produces the format and adds to the result.
Nothing in the API could express that before.
"""

import pytest

from manuskript.media_types import BBCODE, MARKDOWN
from manuskript.plugins import ExtensionDescriptor, OptionField
from manuskript.plugins.api import TransformContribution
from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.execution import (
    PluginExecutionError,
    run_transform,
    run_transforms,
)
from manuskript.plugins.registry import ContributionKind, PluginRegistry
from manuskript.services.plugin_options import InMemoryPluginOptionStore


class Suffix:
    """Appends its own mark, so ordering is visible in the output."""

    def __init__(self, mark):
        self.mark = mark

    def transform(self, content, media_type, options):
        return "{}[{}]".format(content, self.mark)


def transform(extension_id, mark, media_type=MARKDOWN, priority=0,
              options=()):
    return TransformContribution(
        descriptor=ExtensionDescriptor(extension_id, extension_id),
        media_type=media_type,
        engine_factory=lambda mark=mark: Suffix(mark),
        priority=priority,
        options=options,
    )


def registry_with(*contributions, plugin="vendor.plugin"):
    registry = PluginRegistry()
    registrar = registry.registrar(plugin)
    for contribution in contributions:
        registrar.register_transform(contribution)
    registry.install(plugin, registrar.contributions)
    return registry


# ---------------------------------------------------------- the contract

def test_a_transform_names_the_media_type_it_takes_and_returns():
    contribution = transform("vendor.toc", "toc", media_type=MARKDOWN)

    assert contribution.media_type == MARKDOWN


def test_a_transform_without_a_media_type_is_refused():
    with pytest.raises(ValueError):
        TransformContribution(
            descriptor=ExtensionDescriptor("vendor.x", "X"),
            media_type="  ",
            engine_factory=object,
        )


def test_a_transform_is_its_own_kind_of_contribution():
    registry = registry_with(transform("vendor.toc", "toc"))

    assert registry.transforms == (
        registry.contributions(ContributionKind.TRANSFORM)[0],
    )
    # Not a converter: it converts nothing.
    assert registry.converters == ()


def test_registering_the_wrong_type_as_a_transform_is_refused():
    registry = PluginRegistry()
    registrar = registry.registrar("vendor.plugin")

    with pytest.raises(PluginRegistrationError):
        registrar.register_transform(object())


# ------------------------------------------------------------ the search

def test_transforms_are_found_by_media_type():
    registry = registry_with(
        transform("vendor.md", "md", media_type=MARKDOWN),
        transform("vendor.bb", "bb", media_type=BBCODE),
    )

    found = registry.transforms_for(MARKDOWN)

    assert [t.descriptor.id for t in found] == ["vendor.md"]


def test_a_media_type_with_no_middleware_yields_nothing():
    registry = registry_with(transform("vendor.md", "md"))

    assert registry.transforms_for(BBCODE) == ()


def test_transforms_stack_in_priority_order():
    registry = registry_with(
        transform("vendor.late", "late", priority=1),
        transform("vendor.early", "early", priority=9),
    )

    found = registry.transforms_for(MARKDOWN)

    assert [t.descriptor.id for t in found] == [
        "vendor.early", "vendor.late",
    ]


def test_transforms_from_different_plugins_stack_together():
    registry = PluginRegistry()
    for plugin, mark in (("vendor.a", "a"), ("vendor.b", "b")):
        registrar = registry.registrar(plugin)
        registrar.register_transform(
            transform("{}.t".format(plugin), mark)
        )
        registry.install(plugin, registrar.contributions)

    # Neither plugin knows the other exists; the media type is the meeting
    # point, as it is for renderers.
    assert len(registry.transforms_for(MARKDOWN)) == 2


# --------------------------------------------------------------- running

def test_a_transform_receives_content_and_its_media_type():
    seen = []

    class Recorder:
        def transform(self, content, media_type, options):
            seen.append((content, media_type, options))
            return content

    contribution = TransformContribution(
        descriptor=ExtensionDescriptor("vendor.rec", "Recorder"),
        media_type=BBCODE,
        engine_factory=Recorder,
    )

    run_transform(contribution, "[b]x[/b]")

    assert seen == [("[b]x[/b]", BBCODE, {})]


def test_transforms_run_in_order_over_one_document():
    registry = registry_with(
        transform("vendor.second", "second", priority=1),
        transform("vendor.first", "first", priority=9),
    )

    result = run_transforms(registry.transforms_for(MARKDOWN), "body")

    assert result == "body[first][second]"


def test_declared_options_reach_the_transform():
    seen = []

    class Recorder:
        def transform(self, content, media_type, options):
            seen.append(options)
            return content

    contribution = TransformContribution(
        descriptor=ExtensionDescriptor("vendor.rec", "Recorder"),
        media_type=MARKDOWN,
        engine_factory=Recorder,
        options=(OptionField("depth", "Depth", default=2),),
    )
    store = InMemoryPluginOptionStore()
    store.save("vendor.rec", {"depth": 4})

    run_transforms((contribution,), "body", option_store=store)

    assert seen == [{"depth": 4}]


# ---------------------------------------------------------- when it fails

def test_an_engine_without_a_transform_method_is_reported():
    contribution = TransformContribution(
        descriptor=ExtensionDescriptor("vendor.bad", "Bad"),
        media_type=MARKDOWN,
        engine_factory=object,
    )

    with pytest.raises(PluginExecutionError) as error:
        run_transform(contribution, "body")

    assert "transform(content, media_type, options)" in str(error.value)


def test_returning_something_other_than_text_is_reported():
    class WrongShape:
        def transform(self, content, media_type, options):
            return {"content": content}

    contribution = TransformContribution(
        descriptor=ExtensionDescriptor("vendor.wrong", "Wrong"),
        media_type=MARKDOWN,
        engine_factory=WrongShape,
    )

    with pytest.raises(PluginExecutionError) as error:
        run_transform(contribution, "body")

    # Says what a transform is for, not just that the type was wrong.
    assert MARKDOWN in str(error.value)


def test_a_failing_transform_is_skipped_rather_than_losing_the_document():
    class Explodes:
        def transform(self, content, media_type, options):
            raise RuntimeError("boom")

    broken = TransformContribution(
        descriptor=ExtensionDescriptor("vendor.boom", "Boom"),
        media_type=MARKDOWN,
        engine_factory=Explodes,
        priority=9,
    )

    result = run_transforms(
        (broken, transform("vendor.ok", "ok")),
        "body",
    )

    # Middleware adds to a result somebody else produced. Without it the
    # document is still the document.
    assert result == "body[ok]"
