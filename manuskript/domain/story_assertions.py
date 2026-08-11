"""Explicit author assertions, distinct from references and derived facts."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, Tuple

from manuskript.domain.markdown_dsl import SourceSpan


class CanonState(str, Enum):
    CANON = "canon"
    TENTATIVE = "tentative"
    ALTERNATIVE = "alternative"
    DEPRECATED = "deprecated"


class TemporalAxis(str, Enum):
    NARRATIVE = "narrative"
    STORY = "story"


@dataclass(frozen=True)
class StoryReference:
    """Stable identity used by an assertion, not a prose wikilink address."""

    kind: str
    id: str

    def __post_init__(self):
        if not self.kind.strip() or not self.id.strip():
            raise ValueError("Story references require kind and stable ID.")


@dataclass(frozen=True)
class TemporalPoint:
    """One boundary on narrative order or story chronology."""

    axis: TemporalAxis
    reference: Optional[StoryReference] = None
    value: Any = None

    def __post_init__(self):
        object.__setattr__(self, "axis", TemporalAxis(self.axis))
        if (self.reference is None) == (self.value is None):
            raise ValueError(
                "A temporal point requires exactly one reference or value."
            )
        if self.axis is TemporalAxis.NARRATIVE and self.reference is None:
            raise ValueError(
                "Narrative points must reference an outline document."
            )
        if self.axis is TemporalAxis.STORY and self.value is not None:
            if isinstance(self.value, datetime):
                return
            if isinstance(self.value, date):
                return
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("Story times must be ISO-8601 values.")
            normalized = self.value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                datetime.fromisoformat(normalized)
            except ValueError as error:
                raise ValueError("Story times must be ISO-8601 values.") from error

    @classmethod
    def narrative(cls, kind, identifier):
        return cls(
            TemporalAxis.NARRATIVE,
            reference=StoryReference(str(kind), str(identifier)),
        )

    @classmethod
    def story_reference(cls, kind, identifier):
        return cls(
            TemporalAxis.STORY,
            reference=StoryReference(str(kind), str(identifier)),
        )

    @classmethod
    def story_time(cls, value):
        return cls(TemporalAxis.STORY, value=value)


@dataclass(frozen=True)
class TemporalInterval:
    valid_from: Optional[TemporalPoint] = None
    valid_until: Optional[TemporalPoint] = None

    def __post_init__(self):
        if self.valid_from is None and self.valid_until is None:
            raise ValueError("A temporal interval requires a boundary.")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_from.axis is not self.valid_until.axis
        ):
            raise ValueError("Temporal interval boundaries must share an axis.")


class AssertionTermKind(str, Enum):
    REFERENCE = "reference"
    VALUE = "value"


@dataclass(frozen=True)
class AssertionTerm:
    kind: AssertionTermKind
    reference: Optional[StoryReference] = None
    value: Any = None

    def __post_init__(self):
        object.__setattr__(self, "kind", AssertionTermKind(self.kind))
        if self.kind is AssertionTermKind.REFERENCE:
            if self.reference is None:
                raise ValueError("A reference term requires a reference.")
        elif self.reference is not None:
            raise ValueError("A scalar term cannot also contain a reference.")

    @classmethod
    def referencing(cls, kind: str, identifier: str):
        return cls(
            AssertionTermKind.REFERENCE,
            reference=StoryReference(kind, identifier),
        )

    @classmethod
    def scalar(cls, value):
        return cls(AssertionTermKind.VALUE, value=value)


@dataclass(frozen=True)
class AssertionQualifier:
    name: str
    value: Any


@dataclass(frozen=True)
class AssertionProvenance:
    """Where the author made the claim; source span is always derived."""

    document_id: str = ""
    anchor: str = ""
    note: str = ""
    source_span: Optional[SourceSpan] = field(default=None, compare=False)


@dataclass(frozen=True)
class Assertion:
    id: str
    subject: StoryReference
    predicate: str
    object: AssertionTerm
    qualifiers: Tuple[AssertionQualifier, ...] = ()
    provenance: AssertionProvenance = AssertionProvenance()
    canon_state: CanonState = CanonState.CANON
    validity: Optional[TemporalInterval] = None

    def __post_init__(self):
        if not self.id.strip() or not self.predicate.strip():
            raise ValueError("Assertions require stable ID and predicate.")
        object.__setattr__(self, "canon_state", CanonState(self.canon_state))

    @property
    def is_relationship(self) -> bool:
        return self.object.kind is AssertionTermKind.REFERENCE


@dataclass(frozen=True)
class DerivedFact:
    """Disposable rule output that cannot masquerade as author authority."""

    rule_id: str
    assertion: Assertion
    evidence_assertion_ids: Tuple[str, ...]
