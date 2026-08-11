from manuskript.domain.assertion_dsl import encode_assertion_block
from manuskript.domain.assertion_store import AssertionDocument, AssertionStore
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTerm,
    StoryReference,
)


def _claim(identifier="claim-1", subject="mara", target="key"):
    return Assertion(
        identifier,
        StoryReference("entity", subject),
        "possesses",
        AssertionTerm.referencing("entity", target),
    )


def test_store_binds_mandatory_provenance_to_the_authoritative_document():
    store = AssertionStore()
    document = AssertionDocument(
        "scene-18", "Manuscript/Scene 18.md",
        "Transfer.\n\n" + encode_assertion_block(_claim()),
    )

    assertions = store.rebuild((document,), entity_ids=("mara", "key"))

    assert assertions[0].provenance.document_id == "scene-18"
    assert assertions[0].provenance.source_span.extract(document.text).startswith(
        "```manuskript-assertion"
    )
    assert store.relationships("possesses") == assertions
    assert not store.issues


def test_store_reports_duplicate_ids_and_missing_references_without_data_loss():
    first = AssertionDocument(
        "first", "First.md", encode_assertion_block(_claim())
    )
    second = AssertionDocument(
        "second", "Second.md",
        encode_assertion_block(_claim(target="missing")),
    )
    store = AssertionStore()

    assertions = store.rebuild((first, second), entity_ids=("mara", "key"))

    assert len(assertions) == 1
    assert any("Duplicate assertion ID" in item.message for item in store.issues)

    unique = AssertionDocument(
        "second", "Second.md",
        encode_assertion_block(_claim("claim-2", target="missing")),
    )
    store.rebuild((first, unique), entity_ids=("mara", "key"))

    assert len(store.assertions) == 2
    assert any("Missing entity reference" in item.message for item in store.issues)


def test_store_update_rebuilds_derived_state_from_replacement_source():
    store = AssertionStore()
    original = AssertionDocument(
        "scene", "Scene.md", encode_assertion_block(_claim())
    )
    store.rebuild((original,), entity_ids=("mara", "key"))

    store.update(
        AssertionDocument("scene", "Scene.md", "No assertion now.\n"),
        entity_ids=("mara", "key"),
    )

    assert store.assertions == ()
    assert store.documents[0].text == "No assertion now.\n"
