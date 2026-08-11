from manuskript.domain.assertion_dsl import (
    AssertionDslExtension,
    assertions_from_source,
    encode_assertion_block,
    render_story_markdown,
    strip_assertion_blocks,
)
from manuskript.domain.markdown_dsl import MarkdownDslParser
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionProvenance,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
)


def _assertion():
    return Assertion(
        id="assertion-key-owner",
        subject=StoryReference("entity", "mara"),
        predicate="possesses",
        object=AssertionTerm.referencing("entity", "brass-key"),
        qualifiers=(AssertionQualifier("certainty", "explicit"),),
        provenance=AssertionProvenance(
            document_id="scene-18",
            anchor="paragraph:key-transfer",
            note="Mara accepts the key.",
        ),
        canon_state=CanonState.CANON,
    )


def test_assertion_fence_round_trips_author_state_but_not_derived_span():
    assertion = _assertion()
    source = "Before.\n\n" + encode_assertion_block(assertion) + "\nAfter.\n"

    parsed, diagnostics = assertions_from_source(source)

    assert not diagnostics
    assert parsed[0].id == assertion.id
    assert parsed[0].subject == assertion.subject
    assert parsed[0].object == assertion.object
    assert parsed[0].qualifiers == assertion.qualifiers
    assert parsed[0].provenance.document_id == ""
    assert parsed[0].provenance.anchor == "paragraph:key-transfer"
    assert parsed[0].provenance.source_span.extract(source).startswith(
        "```manuskript-assertion"
    )


def test_assertion_is_a_generic_markdown_dsl_node_not_a_wikilink():
    source = encode_assertion_block(_assertion())
    tree = MarkdownDslParser((AssertionDslExtension(),)).parse(source)

    assert not tree.wikilinks
    assert tree.nodes[0].kind == "story-assertion"
    assert tree.nodes[0].attribute("assertion").predicate == "possesses"


def test_malformed_assertion_remains_visible_editable_markdown():
    source = (
        "Prose.\n\n```manuskript-assertion\n"
        "subject: [not a mapping]\n```\n"
    )

    result = AssertionDslExtension().parse(source)

    assert not result.nodes
    assert result.diagnostics[0].severity == "error"
    assert strip_assertion_blocks(source) == source


def test_story_projection_strips_valid_semantics_and_renders_wikilinks():
    source = (
        "Mara held [[Objects/Key|the key]].\n\n"
        + encode_assertion_block(_assertion())
    )

    rendered = render_story_markdown(source)

    assert "manuskript-assertion" not in rendered
    assert "[the key](manuskript:Objects/Key)" in rendered


def test_scalar_assertion_preserves_null_as_an_explicit_value():
    assertion = Assertion(
        "unknown-location",
        StoryReference("entity", "mara"),
        "located_at",
        AssertionTerm.scalar(None),
        canon_state=CanonState.TENTATIVE,
    )

    reopened = assertions_from_source(
        encode_assertion_block(assertion)
    )[0][0]

    assert reopened.object.value is None
    assert reopened.object.reference is None
    assert reopened.canon_state is CanonState.TENTATIVE


def test_assertion_looking_text_inside_a_larger_code_fence_stays_literal():
    source = (
        "````example\n"
        + encode_assertion_block(_assertion())
        + "````\n"
    )

    assertions, diagnostics = assertions_from_source(source)

    assert assertions == ()
    assert diagnostics == ()
    assert strip_assertion_blocks(source) == source
