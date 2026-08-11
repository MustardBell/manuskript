"""Deterministic evidence-backed rules over explicit story assertions."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from manuskript.domain.rule_dsl import CustomRuleKind
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTermKind,
    CanonState,
    StoryReference,
    TemporalAxis,
    TemporalPoint,
)
from manuskript.domain.temporal_story import (
    TemporalFactStatus,
    TemporalOrder,
)


class FindingOutcome(str, Enum):
    CONFLICT = "conflict"
    INDETERMINATE = "indeterminate"


class OverlapState(str, Enum):
    OVERLAPS = "overlaps"
    DISJOINT = "disjoint"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RuleEvidence:
    assertion_id: str
    document_id: str
    source_start: int
    source_end: int
    role: str = "evidence"


@dataclass(frozen=True)
class RuleFinding:
    id: str
    rule_id: str
    rule_label: str
    outcome: FindingOutcome
    severity: str
    message: str
    evidence: Tuple[RuleEvidence, ...]


@dataclass(frozen=True)
class RuleReport:
    findings: Tuple[RuleFinding, ...]
    evaluated_rule_ids: Tuple[str, ...]

    @property
    def conflicts(self):
        return tuple(
            item for item in self.findings
            if item.outcome is FindingOutcome.CONFLICT
        )

    @property
    def indeterminate(self):
        return tuple(
            item for item in self.findings
            if item.outcome is FindingOutcome.INDETERMINATE
        )


class StoryRule:
    id = ""
    label = ""

    def evaluate(self, context):
        raise NotImplementedError


@dataclass(frozen=True)
class StoryRuleContext:
    assertions: object
    chronology: object
    temporal_story: object


class ExclusiveTemporalObjectRule(StoryRule):
    """One scope key cannot have distinct values at overlapping times."""

    def __init__(
        self,
        rule_id,
        label,
        predicate,
        *,
        scope="subject",
        severity="warning",
        message="",
    ):
        self.id = str(rule_id)
        self.label = str(label)
        self.predicate = str(predicate)
        self.scope = str(scope)
        self.severity = str(severity)
        self.message = str(message)

    def evaluate(self, context):
        assertions = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == self.predicate
            and item.object.kind is AssertionTermKind.REFERENCE
        )
        findings = []
        for index, first in enumerate(assertions):
            for second in assertions[index + 1:]:
                if self._scope_key(first) != self._scope_key(second):
                    continue
                if self._value_key(first) == self._value_key(second):
                    continue
                overlap = interval_overlap(
                    first, second, context.chronology
                )
                if overlap is OverlapState.DISJOINT:
                    continue
                outcome = (
                    FindingOutcome.CONFLICT
                    if overlap is OverlapState.OVERLAPS
                    else FindingOutcome.INDETERMINATE
                )
                findings.append(_finding(
                    self,
                    outcome,
                    self.severity if outcome is FindingOutcome.CONFLICT else "info",
                    self.message or self._default_message(outcome),
                    (first, second),
                ))
        return tuple(findings)

    def _scope_key(self, assertion):
        return (
            assertion.subject
            if self.scope == "subject" else assertion.object.reference
        )

    def _value_key(self, assertion):
        return (
            assertion.object.reference
            if self.scope == "subject" else assertion.subject
        )

    def _default_message(self, outcome):
        if outcome is FindingOutcome.INDETERMINATE:
            return (
                "The temporal annotations are insufficient to decide whether "
                "two {} assertions overlap.".format(self.predicate)
            )
        return (
            "Two canonical {} assertions assign different values during "
            "overlapping time.".format(self.predicate)
        )


class RequiresPriorRule(StoryRule):
    """A trigger requires matching explicit state at its start boundary."""

    def __init__(
        self,
        rule_id,
        label,
        trigger_predicate,
        required_predicate,
        *,
        match="subject-object",
        severity="warning",
        message="",
    ):
        self.id = str(rule_id)
        self.label = str(label)
        self.trigger_predicate = str(trigger_predicate)
        self.required_predicate = str(required_predicate)
        self.match = str(match)
        self.severity = str(severity)
        self.message = str(message)

    def evaluate(self, context):
        triggers = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == self.trigger_predicate
        )
        candidates = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == self.required_predicate
        )
        findings = []
        for trigger in triggers:
            point = _start_point(trigger)
            matched = tuple(
                item for item in candidates if self._matches(trigger, item)
            )
            if point is None:
                findings.append(_finding(
                    self,
                    FindingOutcome.INDETERMINATE,
                    "info",
                    "Cannot check {} without a start boundary.".format(
                        self.trigger_predicate
                    ),
                    (trigger,),
                ))
                continue
            states = tuple(
                context.temporal_story.evaluate(item, point)
                for item in matched
            )
            if any(
                state.status is TemporalFactStatus.ACTIVE for state in states
            ):
                continue
            if any(
                state.status is TemporalFactStatus.UNKNOWN for state in states
            ):
                outcome, severity = FindingOutcome.INDETERMINATE, "info"
                message = (
                    "The partial chronology cannot establish the required "
                    "{} state before {}.".format(
                        self.required_predicate, self.trigger_predicate
                    )
                )
            else:
                outcome, severity = FindingOutcome.CONFLICT, self.severity
                message = self.message or (
                    "No active {} assertion supports this {} assertion."
                    .format(self.required_predicate, self.trigger_predicate)
                )
            findings.append(_finding(
                self,
                outcome,
                severity,
                message,
                (trigger,) + matched,
            ))
        return tuple(findings)

    def _matches(self, trigger, candidate):
        if self.match in ("subject", "subject-object"):
            if trigger.subject != candidate.subject:
                return False
        if self.match in ("object", "subject-object"):
            if trigger.object != candidate.object:
                return False
        return True


class TransferBeforePossessionRule(StoryRule):
    id = "ownership.transfer-before-possession"
    label = "Transfer before possession"

    def evaluate(self, context):
        transfers = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == "transfers"
            and item.object.reference is not None
        )
        findings = []
        for possession in context.assertions.assertions:
            if (
                possession.canon_state is not CanonState.CANON
                or possession.predicate != "possesses"
                or possession.object.reference is None
                or _qualifier(possession, "initial", False)
            ):
                continue
            start = _start_point(possession)
            if start is None:
                continue
            matched = tuple(
                item for item in transfers
                if item.object.reference == possession.object.reference
                and _qualifier_reference(item, "to") == possession.subject
            )
            orders = tuple(
                _point_order(_start_point(item), start, context.chronology)
                for item in matched
            )
            if any(order in (TemporalOrder.BEFORE, TemporalOrder.SAME) for order in orders):
                continue
            if matched and any(order is TemporalOrder.UNKNOWN for order in orders):
                outcome, severity = FindingOutcome.INDETERMINATE, "info"
                message = "A matching transfer exists, but its order is unknown."
            else:
                outcome, severity = FindingOutcome.CONFLICT, "warning"
                message = (
                    "Possession begins without a preceding transfer to the "
                    "new possessor; mark initial state explicitly if intended."
                )
            findings.append(_finding(
                self, outcome, severity, message, (possession,) + matched
            ))
        return tuple(findings)


class CausalityRule(StoryRule):
    id = "causality.order-and-cycles"
    label = "Causality order and cycles"

    def evaluate(self, context):
        causes = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == "causes"
            and item.object.reference is not None
        )
        findings = []
        for assertion in causes:
            target = assertion.object.reference
            if assertion.subject == target:
                findings.append(_finding(
                    self,
                    FindingOutcome.CONFLICT,
                    "warning",
                    "A cause directly references itself.",
                    (assertion,),
                ))
                continue
            if (
                assertion.subject.kind in ("document", "entity")
                and target.kind in ("document", "entity")
            ):
                order = context.chronology.compare(
                    TemporalPoint.story_reference(
                        assertion.subject.kind, assertion.subject.id
                    ),
                    TemporalPoint.story_reference(target.kind, target.id),
                )
                if order is TemporalOrder.AFTER:
                    findings.append(_finding(
                        self,
                        FindingOutcome.CONFLICT,
                        "warning",
                        "The explicit cause occurs after its effect.",
                        (assertion,),
                    ))
        findings.extend(self._cycle_findings(causes))
        return tuple(findings)

    def _cycle_findings(self, causes):
        edges = {}
        evidence = {}
        for assertion in causes:
            if assertion.subject == assertion.object.reference:
                continue
            edges.setdefault(assertion.subject, set()).add(
                assertion.object.reference
            )
            evidence[(assertion.subject, assertion.object.reference)] = assertion
        cycles = []
        visited = set()
        active = []
        active_set = set()

        def visit(node):
            visited.add(node)
            active.append(node)
            active_set.add(node)
            for target in sorted(
                edges.get(node, ()), key=lambda item: (item.kind, item.id)
            ):
                if target not in visited:
                    visit(target)
                elif target in active_set:
                    start = active.index(target)
                    cycle = tuple(active[start:] + [target])
                    signature = tuple(
                        sorted((item.kind, item.id) for item in cycle[:-1])
                    )
                    if signature not in {item[0] for item in cycles}:
                        cycle_evidence = tuple(
                            evidence[(cycle[index], cycle[index + 1])]
                            for index in range(len(cycle) - 1)
                        )
                        cycles.append((signature, cycle_evidence))
            active.pop()
            active_set.remove(node)

        for node in sorted(edges, key=lambda item: (item.kind, item.id)):
            if node not in visited:
                visit(node)
        return tuple(
            _finding(
                self,
                FindingOutcome.CONFLICT,
                "warning",
                "The explicit causality graph contains a cycle.",
                cycle_evidence,
            )
            for _signature, cycle_evidence in cycles
        )


class TravelTimeRule(StoryRule):
    id = "location.minimum-travel-time"
    label = "Minimum travel time"

    def evaluate(self, context):
        constraints = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == "travel_time"
            and item.object.reference is not None
        )
        locations = tuple(
            item for item in context.assertions.assertions
            if item.canon_state is CanonState.CANON
            and item.predicate == "located_at"
            and item.object.reference is not None
        )
        findings = []
        for first in locations:
            for second in locations:
                if (
                    first.id >= second.id
                    or first.subject != second.subject
                    or first.object.reference == second.object.reference
                ):
                    continue
                transition = _ordered_transition(first, second, context.chronology)
                if transition is None:
                    continue
                origin, destination, gap = transition
                constraint = next((
                    item for item in constraints
                    if _constraint_matches(
                        item,
                        origin.object.reference,
                        destination.object.reference,
                    )
                ), None)
                if constraint is None or gap is None:
                    continue
                minimum = _qualifier(constraint, "minimum_minutes", None)
                try:
                    minimum_seconds = float(minimum) * 60.0
                except (TypeError, ValueError):
                    continue
                if gap.total_seconds() < minimum_seconds:
                    findings.append(_finding(
                        self,
                        FindingOutcome.CONFLICT,
                        "warning",
                        "The annotated transition is shorter than the explicit "
                        "minimum travel time.",
                        (origin, destination, constraint),
                    ))
        return tuple(findings)


class StoryRuleEngine:
    def __init__(self, assertions, chronology, temporal_story, rule_store=None):
        self._context = StoryRuleContext(
            assertions, chronology, temporal_story
        )
        self._ruleStore = rule_store
        self._builtins = (
            ExclusiveTemporalObjectRule(
                "location.exclusive",
                "One location at a time",
                "located_at",
            ),
            ExclusiveTemporalObjectRule(
                "ownership.exclusive",
                "One possessor at a time",
                "possesses",
                scope="object",
            ),
            RequiresPriorRule(
                "knowledge.precedes-use",
                "Knowledge precedes use",
                "uses_knowledge",
                "knows",
            ),
            TransferBeforePossessionRule(),
            CausalityRule(),
            TravelTimeRule(),
        )

    @property
    def rules(self):
        custom = tuple(
            self._custom_rule(item)
            for item in (
                self._ruleStore.rules if self._ruleStore is not None else ()
            )
        )
        return self._builtins + custom

    def run(self, rule_ids=()):
        selected = set(str(item) for item in rule_ids)
        rules = tuple(
            rule for rule in self.rules if not selected or rule.id in selected
        )
        findings = []
        for rule in rules:
            findings.extend(rule.evaluate(self._context))
        return RuleReport(
            tuple(sorted(
                findings,
                key=lambda item: (
                    item.rule_id,
                    item.id,
                ),
            )),
            tuple(rule.id for rule in rules),
        )

    @staticmethod
    def _custom_rule(definition):
        if definition.kind is CustomRuleKind.EXCLUSIVE_OBJECT:
            return ExclusiveTemporalObjectRule(
                definition.id,
                definition.label,
                definition.predicate,
                scope=definition.scope,
                severity=definition.severity,
                message=definition.message,
            )
        return RequiresPriorRule(
            definition.id,
            definition.label,
            definition.trigger_predicate,
            definition.required_predicate,
            match=definition.match,
            severity=definition.severity,
            message=definition.message,
        )


def interval_overlap(first, second, chronology):
    first_interval = first.validity
    second_interval = second.validity
    if first_interval is None or second_interval is None:
        return OverlapState.OVERLAPS
    first_axis = _interval_axis(first_interval)
    second_axis = _interval_axis(second_interval)
    if first_axis is not second_axis:
        return OverlapState.UNKNOWN
    comparisons = []
    if (
        first_interval.valid_until is not None
        and second_interval.valid_from is not None
    ):
        comparisons.append(chronology.compare(
            first_interval.valid_until, second_interval.valid_from
        ))
    if (
        second_interval.valid_until is not None
        and first_interval.valid_from is not None
    ):
        comparisons.append(chronology.compare(
            second_interval.valid_until, first_interval.valid_from
        ))
    if TemporalOrder.BEFORE in comparisons:
        return OverlapState.DISJOINT
    if TemporalOrder.UNKNOWN in comparisons:
        return OverlapState.UNKNOWN
    return OverlapState.OVERLAPS


def _interval_axis(interval):
    point = interval.valid_from or interval.valid_until
    return point.axis if point is not None else None


def _start_point(assertion):
    return (
        assertion.validity.valid_from
        if assertion.validity is not None else None
    )


def _point_order(first, second, chronology):
    if first is None or second is None:
        return TemporalOrder.UNKNOWN
    return chronology.compare(first, second)


def _qualifier(assertion, name, default=None):
    return next(
        (item.value for item in assertion.qualifiers if item.name == name),
        default,
    )


def _qualifier_reference(assertion, name):
    value = _qualifier(assertion, name)
    if isinstance(value, StoryReference):
        return value
    if isinstance(value, dict) and "kind" in value and "id" in value:
        try:
            return StoryReference(str(value["kind"]), str(value["id"]))
        except ValueError:
            return None
    return None


def _evidence(assertion, role="evidence"):
    span = assertion.provenance.source_span
    return RuleEvidence(
        assertion.id,
        assertion.provenance.document_id,
        span.start if span is not None else 0,
        span.end if span is not None else 0,
        role,
    )


def _finding(rule, outcome, severity, message, assertions):
    evidence = tuple(_evidence(item) for item in assertions)
    identifier = "{}:{}".format(
        rule.id,
        ":".join(sorted(item.assertion_id for item in evidence)),
    )
    return RuleFinding(
        identifier,
        rule.id,
        rule.label,
        outcome,
        severity,
        message,
        evidence,
    )


def _constraint_matches(assertion, origin, destination):
    if assertion.subject == origin and assertion.object.reference == destination:
        return True
    return bool(
        _qualifier(assertion, "bidirectional", False)
        and assertion.subject == destination
        and assertion.object.reference == origin
    )


def _ordered_transition(first, second, chronology):
    first_end = first.validity.valid_until if first.validity is not None else None
    second_start = (
        second.validity.valid_from if second.validity is not None else None
    )
    reverse_end = (
        second.validity.valid_until if second.validity is not None else None
    )
    reverse_start = (
        first.validity.valid_from if first.validity is not None else None
    )
    if first_end is not None and second_start is not None:
        order = chronology.compare(first_end, second_start)
        if order in (TemporalOrder.BEFORE, TemporalOrder.SAME):
            return first, second, _story_gap(first_end, second_start, chronology)
    if reverse_end is not None and reverse_start is not None:
        order = chronology.compare(reverse_end, reverse_start)
        if order in (TemporalOrder.BEFORE, TemporalOrder.SAME):
            return second, first, _story_gap(
                reverse_end, reverse_start, chronology
            )
    return None


def _story_gap(first, second, chronology):
    if first.axis is not TemporalAxis.STORY or second.axis is not TemporalAxis.STORY:
        return None
    first_range = chronology.time_range(first)
    second_range = chronology.time_range(second)
    if first_range is None or second_range is None:
        return None
    try:
        return second_range[0] - first_range[1]
    except TypeError:
        return None
