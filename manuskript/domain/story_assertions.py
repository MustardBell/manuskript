"""Explicit author assertions, distinct from references and derived facts."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Tuple

from manuskript.domain.markdown_dsl import SourceSpan


class CanonState(str, Enum):
    CANON = "canon"
    TENTATIVE = "tentative"
    ALTERNATIVE = "alternative"
    DEPRECATED = "deprecated"


@dataclass(frozen=True)
class StoryReference:
    """Stable identity used by an assertion, not a prose wikilink address."""

    kind: str
    id: str

    def __post_init__(self):
        if not self.kind.strip() or not self.id.strip():
            raise ValueError("Story references require kind and stable ID.")


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
