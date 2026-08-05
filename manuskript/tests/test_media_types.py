"""Declaring a format, promising something about it, and resolving it.

These three are separate acts, and most of what follows is proof that they
stay separate: declaring promises nothing, a promise about an undeclared
format is refused, and a format nothing produces is inert rather than broken.
"""

import pytest

from manuskript.media_types import (
    CONSUMES,
    CORE,
    PRODUCES,
    TRANSFORMS,
    USER,
    MediaType,
    MediaTypeCycleError,
    MediaTypeError,
    MediaTypeRegistry,
    core_registry,
)


BBCODE = "text/x-bbcode"
MARKDOWN = "text/markdown"
FB2 = "application/x-fictionbook+xml"


def registry():
    return MediaTypeRegistry()


# --------------------------------------------------------------- declaring

def test_declaring_records_the_type_and_its_declarer():
    subject = registry()

    subject.declare(MediaType(BBCODE, "BBCode"), CORE)

    assert subject.is_known(BBCODE)
    assert subject.declared_by(BBCODE) == (CORE,)
    assert subject.label(BBCODE) == "BBCode"


def test_two_origins_declaring_one_type_is_agreement():
    subject = registry()

    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.declare(BBCODE, "vendor.structured-pages")

    # Not a collision, unlike a duplicate contribution ID.
    assert subject.declared_by(BBCODE) == (CORE, "vendor.structured-pages")


def test_declaring_twice_from_one_origin_is_idempotent():
    subject = registry()

    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)

    assert subject.declared_by(BBCODE) == (CORE,)


def test_the_first_namer_supplies_the_attributes():
    subject = registry()

    subject.declare(MediaType(BBCODE, "BBCode", textual=True), CORE)
    subject.declare(MediaType(BBCODE, "Forum markup", textual=False), USER)

    # Conflicting attributes keep the first and do not raise.
    assert subject.get(BBCODE).label == "BBCode"
    assert subject.get(BBCODE).textual is True
    assert subject.declared_by(BBCODE) == (CORE, USER)


def test_bare_interest_can_precede_the_attributes():
    subject = registry()

    subject.declare(FB2, "vendor.reader")

    assert subject.is_known(FB2)
    assert subject.get(FB2).named is False
    # Falls back to the identifier until somebody names it.
    assert subject.label(FB2) == FB2

    subject.declare(MediaType(FB2, "FictionBook 2", textual=False), "vendor.fb2")

    assert subject.get(FB2).named is True
    assert subject.label(FB2) == "FictionBook 2"
    assert subject.declared_by(FB2) == ("vendor.reader", "vendor.fb2")


def test_a_declaration_needs_an_identifier_and_an_origin():
    subject = registry()

    with pytest.raises(MediaTypeError):
        MediaType("   ")
    with pytest.raises(MediaTypeError):
        subject.declare(BBCODE, "  ")


# --------------------------------------------------------------- promising

def test_declaring_promises_nothing():
    subject = registry()

    subject.declare(MediaType(BBCODE, "BBCode"), CORE)

    assert subject.promises(BBCODE) == {
        PRODUCES: (),
        CONSUMES: (),
        TRANSFORMS: (),
    }


def test_one_origin_may_hold_different_promises_for_different_types():
    subject = registry()
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)

    subject.promise(BBCODE, CONSUMES, "vendor.structured-pages")
    subject.promise(MARKDOWN, PRODUCES, "vendor.structured-pages")

    # SAMPLE grabs core's BBCode converter but builds its own Markdown.
    assert subject.promises(BBCODE)[CONSUMES] == ("vendor.structured-pages",)
    assert subject.promises(BBCODE)[PRODUCES] == ()
    assert subject.promises(MARKDOWN)[PRODUCES] == ("vendor.structured-pages",)
    assert subject.promises(MARKDOWN)[CONSUMES] == ()


def test_promised_by_lists_every_type_one_origin_touched():
    subject = registry()
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)
    subject.promise(BBCODE, CONSUMES, "sample")
    subject.promise(MARKDOWN, PRODUCES, "sample")

    assert subject.promised_by("sample") == (MARKDOWN, BBCODE)
    assert subject.promised_by("sample", PRODUCES) == (MARKDOWN,)


def test_a_promise_about_an_undeclared_format_is_refused():
    subject = registry()

    with pytest.raises(MediaTypeError) as error:
        subject.promise(FB2, PRODUCES, "vendor.fb2")

    assert FB2 in str(error.value)


def test_an_unknown_promise_kind_is_refused():
    subject = registry()
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)

    with pytest.raises(MediaTypeError):
        subject.promise(BBCODE, "emits", "vendor.thing")


# ---------------------------------------------------------------- fallbacks

def test_a_type_with_no_base_stands_alone():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)

    assert subject.fallback_chain(MARKDOWN) == (MARKDOWN,)


def test_a_base_seeds_the_default_fallback():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)
    subject.declare(
        MediaType(
            "text/vnd.reddit+markdown",
            "Reddit Markdown",
            base=MARKDOWN,
        ),
        "vendor.reddit",
    )

    assert subject.fallback_chain("text/vnd.reddit+markdown") == (
        "text/vnd.reddit+markdown",
        MARKDOWN,
    )


def test_a_user_assignment_wins_over_the_base():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)
    subject.declare(MediaType("text/plain", "Plain text"), CORE)
    subject.declare(
        MediaType("text/vnd.sv+bbcode", "SV BBCode", base=MARKDOWN),
        "vendor.sv",
    )

    subject.assign_fallback("text/vnd.sv+bbcode", "text/plain")

    assert subject.fallback_chain("text/vnd.sv+bbcode") == (
        "text/vnd.sv+bbcode",
        "text/plain",
    )


def test_unassigning_a_fallback_returns_to_the_base():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)
    subject.declare(MediaType("text/plain", "Plain text"), CORE)
    subject.declare(
        MediaType("text/vnd.sv+bbcode", "SV BBCode", base=MARKDOWN),
        "vendor.sv",
    )
    subject.assign_fallback("text/vnd.sv+bbcode", "text/plain")

    subject.assign_fallback("text/vnd.sv+bbcode", "")

    assert subject.fallback("text/vnd.sv+bbcode") == ""
    assert subject.fallback_chain("text/vnd.sv+bbcode")[-1] == MARKDOWN


def test_falling_back_to_an_undeclared_type_is_refused():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)

    with pytest.raises(MediaTypeError):
        subject.assign_fallback(MARKDOWN, FB2)


# ------------------------------------------------------------------- cycles

def test_a_type_cannot_be_based_on_itself():
    with pytest.raises(MediaTypeCycleError):
        MediaType(MARKDOWN, "Markdown", base=MARKDOWN)


def test_re_declaring_cannot_change_an_existing_base():
    subject = registry()
    subject.declare(MediaType("a/one", "One"), CORE)
    subject.declare(MediaType("a/two", "Two", base="a/one"), CORE)

    # The first namer's attributes stand, so this is ignored rather than
    # refused -- and a loop is therefore unreachable this way.
    subject.declare(MediaType("a/one", "One again", base="a/two"), USER)

    assert subject.get("a/one").base == ""
    assert subject.declared_by("a/one") == (CORE, USER)


def test_a_base_that_would_close_a_loop_is_refused_when_named():
    subject = registry()
    # Somebody declares bare interest before anyone names the format...
    subject.declare("a/one", "vendor.reader")
    subject.declare(MediaType("a/two", "Two", base="a/one"), CORE)

    # ...so the attributes arriving later are the first ones, and this base
    # really would close a loop.
    with pytest.raises(MediaTypeCycleError) as error:
        subject.declare(MediaType("a/one", "One", base="a/two"), USER)

    assert "a/one" in str(error.value)
    assert subject.get("a/one").named is False


def test_a_fallback_that_would_close_a_loop_is_refused():
    subject = registry()
    subject.declare(MediaType("a/one", "One"), CORE)
    subject.declare(MediaType("a/two", "Two"), CORE)
    subject.assign_fallback("a/one", "a/two")

    with pytest.raises(MediaTypeCycleError) as error:
        subject.assign_fallback("a/two", "a/one")

    # Names where the loop closes, not merely that one exists.
    assert "a/two" in str(error.value)


def test_fallback_chain_refuses_a_loop_it_is_handed():
    subject = registry()
    subject.declare(MediaType("a/one", "One"), CORE)
    subject.declare(MediaType("a/two", "Two"), CORE)
    subject.assign_fallback("a/one", "a/two")
    # Bypass the guard the way corrupted stored preferences would.
    subject._fallbacks["a/two"] = "a/one"

    with pytest.raises(MediaTypeCycleError) as error:
        subject.fallback_chain("a/one")

    assert "a/one" in str(error.value)


# ---------------------------------------------------------------- overrides

def test_resolving_follows_an_override():
    subject = registry()
    subject.declare(MediaType("text/plain", "Plain text"), CORE)
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)

    subject.assign_override("text/plain", BBCODE)

    assert subject.resolve("text/plain") == BBCODE
    assert subject.override("text/plain") == BBCODE


def test_an_override_names_who_it_affects():
    subject = registry()
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.declare(BBCODE, "vendor.structured-pages")

    assert subject.affected_by(BBCODE) == (CORE, "vendor.structured-pages")


def test_clearing_an_override_restores_the_identifier():
    subject = registry()
    subject.declare(MediaType("text/plain", "Plain text"), CORE)
    subject.declare(MediaType(BBCODE, "BBCode"), CORE)
    subject.assign_override("text/plain", BBCODE)

    subject.assign_override("text/plain", "")

    assert subject.resolve("text/plain") == "text/plain"


def test_an_override_that_would_close_a_loop_is_refused():
    subject = registry()
    subject.declare(MediaType("a/one", "One"), CORE)
    subject.declare(MediaType("a/two", "Two"), CORE)
    subject.assign_override("a/one", "a/two")

    with pytest.raises(MediaTypeCycleError):
        subject.assign_override("a/two", "a/one")


def test_overriding_to_an_undeclared_type_is_refused():
    subject = registry()
    subject.declare(MediaType("text/plain", "Plain text"), CORE)

    with pytest.raises(MediaTypeError):
        subject.assign_override("text/plain", FB2)


def test_a_fallback_chain_starts_from_the_resolved_type():
    subject = registry()
    subject.declare(MediaType(MARKDOWN, "Markdown"), CORE)
    subject.declare(MediaType("text/plain", "Plain text"), CORE)
    subject.declare(MediaType(BBCODE, "BBCode", base=MARKDOWN), CORE)
    subject.assign_override("text/plain", BBCODE)

    assert subject.fallback_chain("text/plain") == (BBCODE, MARKDOWN)


# ------------------------------------------------------------ core catalogue

def test_core_declares_the_formats_it_exports():
    subject = core_registry()

    for media_id in (
        "text/plain",
        "text/markdown",
        "text/html",
        BBCODE,
        "application/x-latex",
        "text/x-rst",
        "application/epub+zip",
        "application/pdf",
    ):
        assert subject.is_known(media_id), media_id
        assert subject.declared_by(media_id) == (CORE,)


def test_destinations_are_not_textual_representations():
    subject = core_registry()

    for media_id in (
        "application/epub+zip",
        "application/pdf",
        "application/vnd.oasis.opendocument.text",
        "text/x-opml+xml",
    ):
        assert subject.get(media_id).textual is False, media_id

    for media_id in ("text/markdown", "text/html", BBCODE):
        assert subject.get(media_id).textual is True, media_id


def test_bbcode_is_not_reported_as_plain_text():
    subject = core_registry()

    # The BBCode exporter calls itself text/plain today, which collides with
    # actual plain text once media types become the routing key.
    assert subject.get(BBCODE).id != "text/plain"
    assert subject.label("text/plain") == "Plain text"


def test_core_declares_nothing_it_does_not_name():
    subject = core_registry()

    assert all(media_type.named for media_type in subject.known())
