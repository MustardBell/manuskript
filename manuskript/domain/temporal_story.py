"""Deterministic chronology and temporal state derived from assertions."""

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Mapping, Optional, Tuple

from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTermKind,
    CanonState,
    StoryReference,
    TemporalAxis,
    TemporalPoint,
)


CHRONOLOGY_PREDICATE = "occurs_at"


class ChronologyKind(str, Enum):
    UNKNOWN = "unknown"
    RELATIVE = "relative"
    EXACT = "exact"
    RANGE = "range"
    BEFORE = "before"
    AFTER = "after"
    SIMULTANEOUS = "simultaneous"


class TemporalOrder(str, Enum):
    BEFORE = "before"
    SAME = "same"
    AFTER = "after"
    UNKNOWN = "unknown"


class TemporalFactStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChronologyRecord:
    subject: StoryReference
    kind: ChronologyKind
    assertion_id: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    related_to: Optional[StoryReference] = None
    label: str = ""


@dataclass(frozen=True)
class TemporalDiagnostic:
    assertion_id: str
    message: str
    severity: str = "warning"


@dataclass(frozen=True)
class TemporalFact:
    assertion: Assertion
    status: TemporalFactStatus
    reason: str = ""


class ChronologyIndex:
    """Partial story order plus independent manuscript narrative order."""

    def __init__(self):
        self._narrative = {}
        self._records = {}
        self._edges = {}
        self._simultaneous = {}
        self._diagnostics = ()

    @property
    def records(self) -> Tuple[ChronologyRecord, ...]:
        return tuple(self._records.values())

    @property
    def diagnostics(self) -> Tuple[TemporalDiagnostic, ...]:
        return self._diagnostics

    def rebuild(self, assertions=(), narrative_ids=()):
        self._narrative = {
            str(identifier): index
            for index, identifier in enumerate(narrative_ids)
        }
        records = {}
        diagnostics = []
        for assertion in assertions:
            if (
                assertion.predicate != CHRONOLOGY_PREDICATE
                or assertion.canon_state is not CanonState.CANON
            ):
                continue
            try:
                record = self._record_from(assertion)
            except (TypeError, ValueError) as error:
                diagnostics.append(TemporalDiagnostic(
                    assertion.id,
                    "Invalid chronology assertion: {}".format(error),
                    "error",
                ))
                continue
            if record.subject in records:
                diagnostics.append(TemporalDiagnostic(
                    assertion.id,
                    "Duplicate canonical chronology for {}:{}.".format(
                        record.subject.kind, record.subject.id
                    ),
                    "error",
                ))
                continue
            records[record.subject] = record
        self._records = records
        self._diagnostics = tuple(diagnostics)
        self._build_relations()
        return self.records

    def record(self, reference):
        return self._records.get(_reference(reference))

    def compare(self, left: TemporalPoint, right: TemporalPoint):
        if not isinstance(left, TemporalPoint) or not isinstance(
            right, TemporalPoint
        ):
            raise TypeError("Chronology comparisons require temporal points.")
        if left.axis is not right.axis:
            return TemporalOrder.UNKNOWN
        if left == right:
            return TemporalOrder.SAME
        if left.axis is TemporalAxis.NARRATIVE:
            return self._compare_narrative(left, right)
        return self._compare_story(left, right)

    def _compare_narrative(self, left, right):
        if left.reference is None or right.reference is None:
            return TemporalOrder.UNKNOWN
        first = self._narrative.get(left.reference.id)
        second = self._narrative.get(right.reference.id)
        if first is None or second is None:
            return TemporalOrder.UNKNOWN
        return _order(first, second)

    def _compare_story(self, left, right):
        first_ref = left.reference
        second_ref = right.reference
        if first_ref is not None and second_ref is not None:
            if self._same_group(first_ref, second_ref):
                return TemporalOrder.SAME
            if self._reachable(first_ref, second_ref):
                return TemporalOrder.BEFORE
            if self._reachable(second_ref, first_ref):
                return TemporalOrder.AFTER
        first = self._time_range(left)
        second = self._time_range(right)
        if first is None or second is None:
            return TemporalOrder.UNKNOWN
        try:
            if first[1] < second[0]:
                return TemporalOrder.BEFORE
            if first[0] > second[1]:
                return TemporalOrder.AFTER
        except TypeError:
            # A naive local story time and a timezone-aware story time do not
            # share a dependable frame of reference. Incomplete annotation is
            # unknown, never a crash or an invented order.
            return TemporalOrder.UNKNOWN
        if first == second and first[0] == first[1]:
            return TemporalOrder.SAME
        return TemporalOrder.UNKNOWN

    def _time_range(self, point):
        if point.reference is None:
            timestamp = _timestamp(point.value)
            return (timestamp, timestamp) if timestamp is not None else None
        record = self._records.get(point.reference)
        if record is None or record.start is None:
            return None
        return record.start, record.end or record.start

    def _build_relations(self):
        self._edges = {}
        self._simultaneous = {}
        for record in self._records.values():
            if (
                record.kind is ChronologyKind.SIMULTANEOUS
                and record.related_to is not None
            ):
                self._union(record.subject, record.related_to)
        for record in self._records.values():
            related = record.related_to
            if related is None:
                continue
            if record.kind is ChronologyKind.BEFORE:
                self._edge(self._find(record.subject), self._find(related))
            elif record.kind is ChronologyKind.AFTER:
                self._edge(self._find(related), self._find(record.subject))

    def _edge(self, before, after):
        self._edges.setdefault(before, set()).add(after)

    def _reachable(self, start, target):
        start, target = self._find(start), self._find(target)
        pending = list(self._edges.get(start, ()))
        seen = set()
        while pending:
            current = pending.pop()
            current = self._find(current)
            if current == target or self._same_group(current, target):
                return True
            if current in seen:
                continue
            seen.add(current)
            pending.extend(self._edges.get(current, ()))
        return False

    def _find(self, value):
        parent = self._simultaneous.setdefault(value, value)
        if parent != value:
            parent = self._find(parent)
            self._simultaneous[value] = parent
        return parent

    def _union(self, first, second):
        first_root, second_root = self._find(first), self._find(second)
        if first_root != second_root:
            self._simultaneous[second_root] = first_root

    def _same_group(self, first, second):
        if first == second:
            return True
        if first not in self._simultaneous or second not in self._simultaneous:
            return False
        return self._find(first) == self._find(second)

    @staticmethod
    def _record_from(assertion):
        qualifiers = {
            item.name: item.value for item in assertion.qualifiers
        }
        if assertion.object.kind is AssertionTermKind.REFERENCE:
            relation = ChronologyKind(str(qualifiers.get("relation", "")))
            if relation not in (
                ChronologyKind.BEFORE,
                ChronologyKind.AFTER,
                ChronologyKind.SIMULTANEOUS,
            ):
                raise ValueError(
                    "reference chronology requires before, after, or "
                    "simultaneous relation"
                )
            return ChronologyRecord(
                assertion.subject,
                relation,
                assertion.id,
                related_to=assertion.object.reference,
            )
        value = assertion.object.value
        if not isinstance(value, Mapping):
            raise TypeError("chronology value must be a mapping")
        kind = ChronologyKind(str(value.get("kind", "unknown")))
        if kind is ChronologyKind.UNKNOWN:
            return ChronologyRecord(assertion.subject, kind, assertion.id)
        if kind is ChronologyKind.RELATIVE:
            label = str(value.get("label", "")).strip()
            if not label:
                raise ValueError("relative chronology requires a label")
            return ChronologyRecord(
                assertion.subject, kind, assertion.id, label=label
            )
        if kind is ChronologyKind.EXACT:
            start = _required_timestamp(value.get("at"), "exact.at")
            return ChronologyRecord(
                assertion.subject, kind, assertion.id, start, start
            )
        if kind is ChronologyKind.RANGE:
            start = _required_timestamp(value.get("from"), "range.from")
            end = _required_timestamp(value.get("until"), "range.until")
            try:
                reversed_range = end < start
            except TypeError as error:
                raise ValueError(
                    "chronology range mixes local and timezone-aware times"
                ) from error
            if reversed_range:
                raise ValueError("chronology range ends before it starts")
            return ChronologyRecord(
                assertion.subject, kind, assertion.id, start, end
            )
        raise ValueError("relational chronology requires a reference object")


class TemporalStoryIndex:
    """Evaluate generic assertions at a point without inventing facts."""

    def __init__(self, assertions, chronology):
        self.assertions = assertions
        self.chronology = chronology

    def evaluate(self, assertion, at):
        if not isinstance(at, TemporalPoint):
            raise TypeError("Temporal facts require a temporal point.")
        interval = assertion.validity
        if interval is None:
            return TemporalFact(assertion, TemporalFactStatus.ACTIVE)
        if interval.valid_from is not None:
            order = self.chronology.compare(interval.valid_from, at)
            if order is TemporalOrder.AFTER:
                return TemporalFact(
                    assertion,
                    TemporalFactStatus.INACTIVE,
                    "The assertion starts after the requested point.",
                )
            if order is TemporalOrder.UNKNOWN:
                return TemporalFact(
                    assertion,
                    TemporalFactStatus.UNKNOWN,
                    "The start boundary cannot be ordered.",
                )
        if interval.valid_until is not None:
            order = self.chronology.compare(at, interval.valid_until)
            if order is TemporalOrder.AFTER:
                return TemporalFact(
                    assertion,
                    TemporalFactStatus.INACTIVE,
                    "The assertion ended before the requested point.",
                )
            if order is TemporalOrder.UNKNOWN:
                return TemporalFact(
                    assertion,
                    TemporalFactStatus.UNKNOWN,
                    "The end boundary cannot be ordered.",
                )
        return TemporalFact(assertion, TemporalFactStatus.ACTIVE)

    def facts(
        self,
        at,
        *,
        subject=None,
        predicate="",
        include_unknown=True,
    ):
        subject = _reference(subject) if subject is not None else None
        facts = []
        for assertion in self.assertions.assertions:
            if assertion.canon_state is not CanonState.CANON:
                continue
            if subject is not None and assertion.subject != subject:
                continue
            if predicate and assertion.predicate != predicate:
                continue
            fact = self.evaluate(assertion, at)
            if (
                fact.status is TemporalFactStatus.ACTIVE
                or include_unknown
                and fact.status is TemporalFactStatus.UNKNOWN
            ):
                facts.append(fact)
        return tuple(facts)

    def locations(self, subject, at, include_unknown=True):
        return self.facts(
            at,
            subject=subject,
            predicate="located_at",
            include_unknown=include_unknown,
        )

    def possessions(self, subject, at, include_unknown=True):
        return self.facts(
            at,
            subject=subject,
            predicate="possesses",
            include_unknown=include_unknown,
        )

    def relationships(
        self, subject, at, predicate="", include_unknown=True
    ):
        return tuple(
            fact for fact in self.facts(
                at,
                subject=subject,
                predicate=predicate,
                include_unknown=include_unknown,
            )
            if fact.assertion.is_relationship
        )

    def knowledge(self, subject, at, include_unknown=True):
        return self.facts(
            at,
            subject=subject,
            predicate="knows",
            include_unknown=include_unknown,
        )


def _reference(value):
    if isinstance(value, StoryReference):
        return value
    try:
        return StoryReference(str(value.kind), str(value.id))
    except AttributeError as error:
        raise TypeError("A stable story reference is required.") from error


def _timestamp(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _required_timestamp(value: Any, field: str):
    timestamp = _timestamp(value)
    if timestamp is None:
        raise ValueError("{} must be an ISO-8601 story time".format(field))
    return timestamp


def _order(first, second):
    if first < second:
        return TemporalOrder.BEFORE
    if first > second:
        return TemporalOrder.AFTER
    return TemporalOrder.SAME
