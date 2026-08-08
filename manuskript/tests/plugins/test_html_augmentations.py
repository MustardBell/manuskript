"""What a plugin may add to what Markdown means, once it becomes HTML.

Not a transform and not an exporter. A transform is middleware that has to be
told where its output is going; an exporter produces a whole document. An
augmentation says one thing more about Markdown -- lists written ``1)`` were
the case that prompted it -- and every route that renders Markdown as HTML
picks it up.

The first test converts real Markdown through a real extension, because the
whole point is what the reader ends up looking at.
"""

import re

import pytest

from manuskript.plugins.api import (
    ExtensionDescriptor,
    HtmlAugmentationContribution,
)
from manuskript.plugins.errors import PluginRegistrationError
from manuskript.plugins.html_augmentations import markdown_extensions
from manuskript.plugins.registry import PluginRegistry

markdown_module = pytest.importorskip("markdown")


class ParenthesisLists(markdown_module.Extension):
    """Ordered lists written the way people write them: ``1)``.

    Python-Markdown accepts ``1.`` and nothing else, so a list typed with
    parentheses arrives as one run-on paragraph. This rewrites the marker
    before the parser sees it, which is what a preprocessor is for, and
    inserts the blank line the parser also insists on.
    """

    def extendMarkdown(self, md):
        md.preprocessors.register(
            _ParenthesisPreprocessor(md), "parenthesis-lists", 30,
        )


class _ParenthesisPreprocessor(markdown_module.preprocessors.Preprocessor):
    MARKER = re.compile(r"^(\s*)(\d+)\)\s+(.*)$")

    def run(self, lines):
        out = []
        previous_was_item = False
        for line in lines:
            match = self.MARKER.match(line)
            if match is None:
                out.append(line)
                previous_was_item = False
                continue
            if not previous_was_item and out and out[-1].strip():
                # The parser wants a blank line before a list, and a writer
                # does not type one.
                out.append("")
            indent, number, text = match.groups()
            out.append("{}{}. {}".format(indent, number, text))
            previous_was_item = True
        return out


def an_augmentation(
        extension_id="vendor.lists",
        factory=ParenthesisLists,
        page_types=(),
        priority=0):
    return HtmlAugmentationContribution(
        descriptor=ExtensionDescriptor(
            id=extension_id, name="Parenthesis lists",
        ),
        extension_factory=factory,
        page_types=page_types,
        priority=priority,
    )


def registry_with(*contributions):
    registry = PluginRegistry()
    registrar = registry.registrar("vendor.markup")
    for contribution in contributions:
        registrar.register_html_augmentation(contribution)
    registry.install("vendor.markup", registrar.contributions)
    return registry


# ------------------------------------------------------- the whole point

def test_a_list_written_with_parentheses_becomes_a_list():
    """Without the augmentation this is one paragraph, which is the bug."""
    source = "Intro.\n1) First\n2) Second\n3) Third"

    plain = markdown_module.markdown(source)
    augmented = markdown_module.markdown(
        source, extensions=markdown_extensions(registry_with(an_augmentation())),
    )

    assert "<li>" not in plain
    assert augmented.count("<li>") == 3
    assert "<ol>" in augmented
    assert "First" in augmented and "Third" in augmented


def test_prose_is_left_alone():
    """An augmentation that changed ordinary text would be a liability."""
    source = "She counted to 3) and stopped.\n\nA year (1999) went by."

    augmented = markdown_module.markdown(
        source, extensions=markdown_extensions(registry_with(an_augmentation())),
    )

    assert "<li>" not in augmented
    assert "1999" in augmented


# --------------------------------------------------------------- the kind

def test_an_augmentation_needs_something_to_build():
    with pytest.raises(ValueError, match="extension factory"):
        an_augmentation(factory=None)


def test_the_registry_refuses_a_different_kind_of_contribution():
    registry = PluginRegistry()
    registrar = registry.registrar("vendor.markup")

    with pytest.raises(PluginRegistrationError):
        registrar.register_html_augmentation(object())


# --------------------------------------------------------------- the scope

def test_an_augmentation_naming_no_page_type_applies_everywhere():
    registry = registry_with(an_augmentation())

    assert len(registry.html_augmentations_for()) == 1
    assert len(registry.html_augmentations_for("vendor.sample")) == 1


def test_an_augmentation_naming_page_types_applies_only_to_those():
    registry = registry_with(
        an_augmentation(page_types=("vendor.sample",)),
    )

    assert registry.html_augmentations_for() == ()
    assert registry.html_augmentations_for("other.page") == ()
    assert len(registry.html_augmentations_for("vendor.sample")) == 1


def test_augmentations_run_highest_priority_first():
    """So an addition that must see the source before another can say so."""
    registry = registry_with(
        an_augmentation(extension_id="vendor.second", priority=1),
        an_augmentation(extension_id="vendor.first", priority=5),
    )

    order = [
        contribution.descriptor.id
        for contribution in registry.html_augmentations_for()
    ]

    assert order == ["vendor.first", "vendor.second"]


# ------------------------------------------------------------- when it breaks

def test_an_extension_that_will_not_build_is_skipped_not_fatal():
    """A plugin's fault must not be the difference between an export
    happening and not happening.
    """
    def broken():
        raise RuntimeError("no extension today")

    said = []
    registry = registry_with(
        an_augmentation(extension_id="vendor.broken", factory=broken),
        an_augmentation(extension_id="vendor.working", priority=-1),
    )

    built = markdown_extensions(registry, report_error=said.append)

    assert len(built) == 1
    assert isinstance(built[0], ParenthesisLists)
    assert said and "could not be used" in said[0]


def test_no_registry_means_no_augmentations():
    """Rendering without a plugin layer at all is an ordinary case."""
    assert markdown_extensions(None) == []
