from types import SimpleNamespace

from manuskript.domain.assertion_dsl import render_story_markdown
from manuskript.domain.rule_dsl import (
    CustomRuleDefinition,
    CustomRuleKind,
    encode_rule_block,
    rules_from_source,
)
from manuskript.domain.rule_store import RuleDocument, RuleStore
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionProvenance,
    AssertionQualifier,
    AssertionTerm,
    StoryReference,
    TemporalInterval,
    TemporalPoint,
)
from manuskript.domain.story_rules import (
    FindingOutcome,
    StoryRuleEngine,
)
from manuskript.domain.temporal_story import (
    ChronologyIndex,
    TemporalStoryIndex,
)


def _assertion(
    identifier,
    subject,
    predicate,
    object_id,
    *,
    start=None,
    end=None,
    qualifiers=(),
):
    return Assertion(
        identifier,
        StoryReference(*subject),
        predicate,
        AssertionTerm.referencing(*object_id),
        qualifiers=tuple(
            AssertionQualifier(name, value) for name, value in qualifiers
        ),
        provenance=AssertionProvenance(document_id="scene-source"),
        validity=(
            TemporalInterval(start, end)
            if start is not None or end is not None else None
        ),
    )


def _engine(assertions, narrative_ids=(), rules=()):
    store = SimpleNamespace(assertions=tuple(assertions))
    chronology = ChronologyIndex()
    chronology.rebuild(assertions, narrative_ids=narrative_ids)
    temporal = TemporalStoryIndex(store, chronology)
    rule_store = SimpleNamespace(rules=tuple(rules))
    return StoryRuleEngine(store, chronology, temporal, rule_store)


def _narrative(identifier):
    return TemporalPoint.narrative("document", identifier)


def test_custom_rule_dsl_round_trips_and_malformed_source_stays_visible():
    definition = CustomRuleDefinition(
        "wardrobe-exclusive",
        "One uniform at a time",
        CustomRuleKind.EXCLUSIVE_OBJECT,
        predicate="wears",
        severity="error",
    )
    source = "Prose.\n\n" + encode_rule_block(definition)

    rules, diagnostics = rules_from_source(source)

    assert not diagnostics
    assert rules[0].id == definition.id
    assert rules[0].predicate == "wears"
    assert "manuskript-rule" not in render_story_markdown(source)

    malformed = "```manuskript-rule\nid: incomplete\n```\n"
    parsed, diagnostics = rules_from_source(malformed)
    assert parsed == ()
    assert diagnostics[0].severity == "error"
    assert render_story_markdown(malformed) == malformed


def test_rule_store_reports_duplicate_ids_without_losing_source():
    block = encode_rule_block(CustomRuleDefinition(
        "same", "Same", CustomRuleKind.EXCLUSIVE_OBJECT,
        predicate="status",
    ))
    store = RuleStore()

    store.rebuild((
        RuleDocument("one", "One.md", block),
        RuleDocument("two", "Two.md", block),
    ))

    assert len(store.rules) == 1
    assert store.issues[0].document_id == "two"
    assert "Duplicate" in store.issues[0].message


def test_location_and_ownership_rules_report_conflicts_with_evidence():
    ids = ("scene-1", "scene-2", "scene-3", "scene-4")
    assertions = (
        _assertion(
            "mara-vienna", ("entity", "mara"), "located_at",
            ("entity", "vienna"), start=_narrative("scene-1"),
            end=_narrative("scene-3"),
        ),
        _assertion(
            "mara-prague", ("entity", "mara"), "located_at",
            ("entity", "prague"), start=_narrative("scene-2"),
            end=_narrative("scene-4"),
        ),
        _assertion(
            "mara-key", ("entity", "mara"), "possesses",
            ("entity", "key"), start=_narrative("scene-1"),
            end=_narrative("scene-3"), qualifiers=(("initial", True),),
        ),
        _assertion(
            "elias-key", ("entity", "elias"), "possesses",
            ("entity", "key"), start=_narrative("scene-2"),
            end=_narrative("scene-4"), qualifiers=(("initial", True),),
        ),
    )

    report = _engine(assertions, ids).run((
        "location.exclusive", "ownership.exclusive"
    ))

    assert {item.rule_id for item in report.conflicts} == {
        "location.exclusive", "ownership.exclusive"
    }
    assert all(len(item.evidence) == 2 for item in report.conflicts)
    assert all(item.evidence[0].document_id == "scene-source" for item in report.conflicts)


def test_unknown_interval_order_is_an_indeterminate_finding_not_a_conflict():
    assertions = (
        _assertion(
            "one", ("entity", "mara"), "located_at",
            ("entity", "vienna"), start=_narrative("missing-one"),
        ),
        _assertion(
            "two", ("entity", "mara"), "located_at",
            ("entity", "prague"), end=_narrative("missing-two"),
        ),
    )

    report = _engine(assertions, ("known",)).run(("location.exclusive",))

    assert not report.conflicts
    assert report.indeterminate[0].severity == "info"


def test_knowledge_use_requires_matching_active_explicit_knowledge():
    ids = ("scene-1", "scene-2", "scene-3", "scene-4")
    knows = _assertion(
        "knows-code", ("entity", "mara"), "knows",
        ("assertion", "door-code"), start=_narrative("scene-3"),
    )
    early = _assertion(
        "uses-early", ("entity", "mara"), "uses_knowledge",
        ("assertion", "door-code"), start=_narrative("scene-2"),
    )
    later = _assertion(
        "uses-later", ("entity", "mara"), "uses_knowledge",
        ("assertion", "door-code"), start=_narrative("scene-4"),
    )

    report = _engine((knows, early, later), ids).run((
        "knowledge.precedes-use",
    ))

    assert len(report.conflicts) == 1
    assert report.conflicts[0].evidence[0].assertion_id == "uses-early"
    assert {item.assertion_id for item in report.conflicts[0].evidence} == {
        "uses-early", "knows-code"
    }


def test_possession_requires_explicit_transfer_unless_marked_initial():
    ids = ("scene-1", "scene-2", "scene-3")
    transfer = _assertion(
        "transfer", ("entity", "elias"), "transfers",
        ("entity", "key"), start=_narrative("scene-2"),
        qualifiers=(("to", {"kind": "entity", "id": "mara"}),),
    )
    supported = _assertion(
        "supported", ("entity", "mara"), "possesses",
        ("entity", "key"), start=_narrative("scene-3"),
    )
    unsupported = _assertion(
        "unsupported", ("entity", "mara"), "possesses",
        ("entity", "coin"), start=_narrative("scene-3"),
    )
    initial = _assertion(
        "initial", ("entity", "mara"), "possesses",
        ("entity", "coat"), start=_narrative("scene-1"),
        qualifiers=(("initial", True),),
    )

    report = _engine(
        (transfer, supported, unsupported, initial), ids
    ).run(("ownership.transfer-before-possession",))

    assert len(report.conflicts) == 1
    assert report.conflicts[0].evidence[0].assertion_id == "unsupported"


def test_causality_reports_reverse_time_and_cycles_from_explicit_edges():
    chronology = (
        Assertion(
            "time-a", StoryReference("document", "a"), "occurs_at",
            AssertionTerm.scalar({"kind": "exact", "at": "1914-01-02"}),
        ),
        Assertion(
            "time-b", StoryReference("document", "b"), "occurs_at",
            AssertionTerm.scalar({"kind": "exact", "at": "1914-01-01"}),
        ),
    )
    causes = (
        _assertion("a-causes-b", ("document", "a"), "causes", ("document", "b")),
        _assertion("b-causes-a", ("document", "b"), "causes", ("document", "a")),
    )

    report = _engine(chronology + causes).run((
        "causality.order-and-cycles",
    ))

    assert any("after" in item.message for item in report.conflicts)
    assert any("cycle" in item.message for item in report.conflicts)


def test_travel_rule_uses_explicit_minimum_and_known_story_times():
    origin = _assertion(
        "origin", ("entity", "mara"), "located_at",
        ("entity", "vienna"),
        start=TemporalPoint.story_time("1914-01-01T09:00:00"),
        end=TemporalPoint.story_time("1914-01-01T10:00:00"),
    )
    destination = _assertion(
        "destination", ("entity", "mara"), "located_at",
        ("entity", "prague"),
        start=TemporalPoint.story_time("1914-01-01T10:30:00"),
    )
    constraint = _assertion(
        "travel", ("entity", "vienna"), "travel_time",
        ("entity", "prague"), qualifiers=(("minimum_minutes", 60),),
    )

    report = _engine((origin, destination, constraint)).run((
        "location.minimum-travel-time",
    ))

    assert len(report.conflicts) == 1
    assert len(report.conflicts[0].evidence) == 3


def test_custom_rule_definitions_compile_to_safe_generic_rules():
    definition = CustomRuleDefinition(
        "wardrobe-exclusive",
        "One uniform at a time",
        CustomRuleKind.EXCLUSIVE_OBJECT,
        predicate="wears",
        severity="error",
        message="The uniforms overlap.",
    )
    assertions = (
        _assertion("one", ("entity", "mara"), "wears", ("entity", "red")),
        _assertion("two", ("entity", "mara"), "wears", ("entity", "blue")),
    )

    report = _engine(assertions, rules=(definition,)).run((
        "wardrobe-exclusive",
    ))

    assert report.conflicts[0].severity == "error"
    assert report.conflicts[0].message == "The uniforms overlap."
