"""A plugin must not be handed documents it does not own.

Recognising a page type is a cold-start problem: before any property marks
an item, something has to look at the text, and only the plugin knows its own
format. Declaring the format instead of inspecting the text resolves that —
the plugin stays the authority, core does the matching, and plugin code never
sees a foreign document.
"""

import pytest

from manuskript.plugins.api import ContentSignature, PageTypeContribution
from manuskript.plugins.api import ExtensionDescriptor
from manuskript.ui.plugins.page_types import (
    RECOGNITION_WINDOW,
    PageTypeService,
    matches_signature,
)


SAMPLE = ContentSignature(
    starts_with=r"^SAMPLE Interlude",
    ends_with=r"^END SAMPLE Interlude",
)


class Item:
    """Enough of an outline item for recognition."""

    def __init__(self, text, kind="md", properties=None):
        self._text = text
        self._kind = kind
        self._properties = dict(properties or {})

    def text(self):
        return self._text

    def type(self):
        return self._kind

    def hasPluginValue(self, key):
        return key in self._properties

    def pluginValue(self, key):
        return self._properties[key]


def contribution(signature=None, detector=None):
    return PageTypeContribution(
        descriptor=ExtensionDescriptor(id="x.page", name="X page"),
        property_label="X page",
        signature=signature,
        detector=detector,
        parser_factory=object,
    )


def service():
    class Registry:
        page_types = ()
    return PageTypeService(Registry())


# ------------------------------------------------------------- the matcher

def test_all_declared_parts_must_match():
    assert matches_signature(
        SAMPLE, "SAMPLE Interlude #1\nbody\nEND SAMPLE Interlude #1\n")
    assert not matches_signature(SAMPLE, "SAMPLE Interlude #1\nbody\n")
    assert not matches_signature(SAMPLE, "body\nEND SAMPLE Interlude #1\n")


def test_line_endings_do_not_matter():
    assert matches_signature(
        SAMPLE, "SAMPLE Interlude\r\nbody\r\nEND SAMPLE Interlude\r\n")
    assert matches_signature(
        SAMPLE, "SAMPLE Interlude\rbody\rEND SAMPLE Interlude\r")


def test_contains_requires_every_pattern():
    signature = ContentSignature(contains=(r"^alpha$", r"^beta$"))

    assert matches_signature(signature, "alpha\nbeta\n")
    assert not matches_signature(signature, "alpha\n")


def test_a_broken_pattern_does_not_claim_the_document():
    signature = ContentSignature(starts_with=r"^([unclosed")

    assert not matches_signature(signature, "anything")


def test_empty_and_missing_text_match_nothing():
    for value in ("", None):
        assert not matches_signature(SAMPLE, value)


# ------------------------------------------------- no plugin code involved

def test_a_signature_recognises_without_running_plugin_code():
    def must_not_run(_text):
        raise AssertionError("core must match the signature itself")

    page_type = contribution(signature=SAMPLE, detector=must_not_run)
    owned = Item("SAMPLE Interlude\nx\nEND SAMPLE Interlude\n")
    foreign = Item("Just an ordinary scene.")

    assert service().is_enabled(owned, page_type) is True
    assert service().is_enabled(foreign, page_type) is False


def test_a_recorded_property_skips_recognition_entirely():
    def must_not_run(_text):
        raise AssertionError("a decided item must not be re-examined")

    page_type = contribution(signature=SAMPLE, detector=must_not_run)
    decided = Item("anything at all", properties={"x.page": True})
    refused = Item(
        "SAMPLE Interlude\nx\nEND SAMPLE Interlude\n",
        properties={"x.page": False},
    )

    # An explicit answer wins over the signature in both directions.
    assert service().is_enabled(decided, page_type) is True
    assert service().is_enabled(refused, page_type) is False


# ------------------------------------------- the bounded callable fallback

def test_a_callable_detector_sees_only_a_bounded_window():
    seen = []

    def detector(text):
        seen.append(text)
        return False

    body = "SECRET" * 20000
    item = Item("HEAD" + body + "TAIL")

    service().is_enabled(item, contribution(detector=detector))

    window = seen[0]
    assert len(window) <= 2 * RECOGNITION_WINDOW + 1
    assert window.startswith("HEAD")
    assert window.endswith("TAIL")
    # The middle of the document never reaches the plugin.
    assert len(window) < len(item.text())


def test_a_short_document_is_passed_whole():
    seen = []
    item = Item("SAMPLE Interlude\nx\nEND SAMPLE Interlude\n")

    service().is_enabled(
        item, contribution(detector=lambda t: seen.append(t) or False)
    )

    assert seen[0] == item.text()


def test_a_raising_detector_does_not_claim_the_document():
    reported = []
    page_type = contribution(
        detector=lambda _t: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    subject = PageTypeService(
        type("R", (), {"page_types": ()})(),
        report_error=lambda message, *a: reported.append(message),
    )

    assert subject.is_enabled(Item("x"), page_type) is False
    assert reported


# ---------------------------------------------------------------- contract

def test_a_signature_must_declare_something():
    with pytest.raises(ValueError):
        ContentSignature()


def test_a_page_type_may_declare_neither_and_recognise_nothing():
    page_type = contribution()

    assert service().is_enabled(Item("anything"), page_type) is False
