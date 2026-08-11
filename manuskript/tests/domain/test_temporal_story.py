from manuskript.domain.assertion_store import AssertionStore
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
    TemporalInterval,
    TemporalPoint,
)
from manuskript.domain.temporal_story import (
    ChronologyIndex,
    ChronologyKind,
    TemporalFactStatus,
    TemporalOrder,
    TemporalStoryIndex,
)


def _chronology(identifier, subject, value=None, related=None, relation=""):
    return Assertion(
        identifier,
        StoryReference("document", subject),
        "occurs_at",
        (
            AssertionTerm.referencing("document", related)
            if related is not None else AssertionTerm.scalar(value)
        ),
        qualifiers=(
            (AssertionQualifier("relation", relation),) if relation else ()
        ),
    )


def _fact(identifier, predicate, start=None, end=None, canon=CanonState.CANON):
    validity = (
        TemporalInterval(start, end) if start is not None or end is not None
        else None
    )
    return Assertion(
        identifier,
        StoryReference("entity", "mara"),
        predicate,
        AssertionTerm.referencing("entity", "vienna"),
        canon_state=canon,
        validity=validity,
    )


def test_narrative_order_is_independent_from_story_chronology():
    index = ChronologyIndex()
    index.rebuild(
        (
            _chronology("c-last", "last", {"kind": "exact", "at": "1914-01-01"}),
            _chronology("c-first", "first", {"kind": "exact", "at": "1915-01-01"}),
        ),
        narrative_ids=("first", "last"),
    )

    first_narrative = TemporalPoint.narrative("document", "first")
    last_narrative = TemporalPoint.narrative("document", "last")
    first_story = TemporalPoint.story_reference("document", "first")
    last_story = TemporalPoint.story_reference("document", "last")

    assert index.compare(first_narrative, last_narrative) is TemporalOrder.BEFORE
    assert index.compare(first_story, last_story) is TemporalOrder.AFTER
    assert index.compare(first_narrative, first_story) is TemporalOrder.UNKNOWN


def test_partial_chronology_supports_ranges_relations_and_simultaneity():
    index = ChronologyIndex()
    index.rebuild((
        _chronology("a", "a", {"kind": "range", "from": "1914-01-01", "until": "1914-01-03"}),
        _chronology("b", "b", related="a", relation="after"),
        _chronology("c", "c", related="b", relation="after"),
        _chronology("d", "d", related="c", relation="simultaneous"),
    ))

    point = lambda value: TemporalPoint.story_reference("document", value)

    assert index.compare(point("a"), point("c")) is TemporalOrder.BEFORE
    assert index.compare(point("c"), point("d")) is TemporalOrder.SAME
    assert index.compare(point("b"), point("d")) is TemporalOrder.BEFORE
    assert index.record(StoryReference("document", "a")).kind is ChronologyKind.RANGE


def test_incomplete_and_incompatible_chronology_degrades_to_unknown():
    index = ChronologyIndex()
    index.rebuild((
        _chronology("unknown", "unknown", {"kind": "unknown"}),
        _chronology("relative", "relative", {"kind": "relative", "label": "later"}),
    ))

    unknown = TemporalPoint.story_reference("document", "unknown")
    relative = TemporalPoint.story_reference("document", "relative")
    local = TemporalPoint.story_time("1914-01-01T12:00:00")
    aware = TemporalPoint.story_time("1914-01-01T12:00:00Z")

    assert index.compare(unknown, relative) is TemporalOrder.UNKNOWN
    assert index.compare(local, aware) is TemporalOrder.UNKNOWN


def test_invalid_and_duplicate_chronology_are_diagnostics_not_crashes():
    index = ChronologyIndex()
    records = index.rebuild((
        _chronology("good", "scene", {"kind": "exact", "at": "1914-01-01"}),
        _chronology("duplicate", "scene", {"kind": "unknown"}),
        _chronology("bad", "other", {"kind": "range", "from": "later", "until": "never"}),
    ))

    assert tuple(item.assertion_id for item in records) == ("good",)
    assert {item.assertion_id for item in index.diagnostics} == {"duplicate", "bad"}


def test_temporal_generic_facts_report_active_inactive_and_unknown_state():
    start = TemporalPoint.narrative("document", "scene-2")
    end = TemporalPoint.narrative("document", "scene-4")
    active = _fact("location", "located_at", start, end)
    possession = _fact("possession", "possesses", start)
    relationship = _fact("trust", "trusts", start, end)
    knowledge = _fact("knowledge", "knows", start)
    ignored = _fact("alternative", "located_at", start, canon=CanonState.ALTERNATIVE)
    store = AssertionStore()
    store._assertions = (active, possession, relationship, knowledge, ignored)
    chronology = ChronologyIndex()
    chronology.rebuild((), narrative_ids=("scene-1", "scene-2", "scene-3", "scene-4", "scene-5"))
    temporal = TemporalStoryIndex(store, chronology)

    scene_3 = TemporalPoint.narrative("document", "scene-3")
    scene_5 = TemporalPoint.narrative("document", "scene-5")
    missing = TemporalPoint.narrative("document", "missing")

    assert temporal.locations(StoryReference("entity", "mara"), scene_3)[0].status is TemporalFactStatus.ACTIVE
    assert temporal.evaluate(active, scene_5).status is TemporalFactStatus.INACTIVE
    assert temporal.evaluate(active, missing).status is TemporalFactStatus.UNKNOWN
    assert temporal.possessions(StoryReference("entity", "mara"), scene_3)[0].assertion.id == "possession"
    assert temporal.relationships(
        StoryReference("entity", "mara"), scene_3, "trusts"
    )[0].assertion.id == "trust"
    assert temporal.knowledge(StoryReference("entity", "mara"), scene_3)[0].assertion.id == "knowledge"
    assert len(temporal.locations(StoryReference("entity", "mara"), scene_3)) == 1
