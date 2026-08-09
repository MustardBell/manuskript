"""What an exporter does with the additions plugins contributed.

Each Manuskript exporter converts the same Markdown into its own format, so
each has its own route and its own set of applicable additions. The point of
these tests is that the exporters agree about how to find them: one of them
asking and the next not is how an addition contributed for BBCode came to be
applied nowhere at all.
"""

import re

import pytest

from manuskript.exporter.manuskript.BBCode import BBCode
from manuskript.exporter.manuskript.HTML import HTML
from manuskript.exporter.manuskript.markdown import markdown
from manuskript.media_types import BBCODE, HTML as HTML_MEDIA_TYPE, MARKDOWN
from manuskript.plugins import MarkupRule


#: The text-tidying settings every exporter runs before its own conversion,
#: all of them off, so what a test sees is the conversion and nothing else.
NO_TRANSFORMS = {
    "Transform": {
        "Dash": False,
        "Ellipse": False,
        "Spaces": False,
        "Custom": [],
        "DoubleQuotes": "",
        "SingleQuote": "",
    },
}


class Context:
    """An export context that records what it was asked for."""

    def __init__(self, additions=()):
        self.requests = []
        self._additions = list(additions)

    def conversion_augmentations(self, request):
        self.requests.append(request)
        return list(self._additions)


def exporter(kind, context):
    made = kind.__new__(kind)
    made.context = context
    return made


@pytest.mark.parametrize("kind, target", [
    (HTML, HTML_MEDIA_TYPE),
    (BBCode, BBCODE),
    (markdown, MARKDOWN),
])
def test_an_exporter_asks_for_its_own_route(kind, target):
    """From Manuskript's Markdown to whatever this exporter produces. The
    exporter knows both, and nothing else has to be told.
    """
    context = Context()

    assert exporter(kind, context).augmentations() == []
    assert len(context.requests) == 1
    assert context.requests[0].source_format == MARKDOWN
    assert context.requests[0].target_format == target


def test_a_context_offering_nothing_is_not_an_error():
    """Exporting is possible with no plugin layer at all."""

    class Bare:
        pass

    assert exporter(HTML, Bare()).augmentations() == []


def test_a_context_that_raises_does_not_stop_an_export():
    """A plugin's fault must not be the difference between exporting and
    not. The export goes ahead without the additions.
    """

    class Broken:
        def conversion_augmentations(self, request):
            raise RuntimeError("no")

    assert exporter(BBCode, Broken()).augmentations() == []


def test_the_bbcode_exporter_applies_a_rule_contributed_for_its_route():
    """The regression this test exists for: the exporter converted with
    core's rules alone, so an addition declared for Markdown to BBCode was
    registered, filtered, offered -- and never asked for.
    """
    shouting = MarkupRule(r"quiet", "LOUD", re.IGNORECASE)
    made = exporter(BBCode, Context([shouting]))

    converted = made.processText("A quiet word.", NO_TRANSFORMS)

    assert "LOUD" in converted
