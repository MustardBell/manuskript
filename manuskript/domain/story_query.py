"""Typed set-based query AST over entities, references, and assertions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Protocol, Tuple

from manuskript.domain.story_assertions import (
    AssertionTermKind,
    CanonState,
    StoryReference,
)


class QueryScope(str, Enum):
    ASSERTION = "assertion"
    DOCUMENT = "document"
    ENTITY = "entity"


@dataclass(frozen=True, order=True)
class QueryResult:
    scope: QueryScope
    id: str


class QueryExpression(Protocol):
    scope: QueryScope

    def evaluate(self, engine) -> frozenset:
        ...


@dataclass(frozen=True)
class All(QueryExpression):
    scope: QueryScope

    def __post_init__(self):
        object.__setattr__(self, "scope", QueryScope(self.scope))

    def evaluate(self, engine):
        return engine.universe(self.scope)


@dataclass(frozen=True)
class AssertionsWhere(QueryExpression):
    subject: Optional[StoryReference] = None
    predicate: str = ""
    object_reference: Optional[StoryReference] = None
    canon_states: Tuple[CanonState, ...] = ()
    source_document_ids: Tuple[str, ...] = ()
    qualifiers: Tuple[Tuple[str, object], ...] = ()

    @property
    def scope(self):
        return QueryScope.ASSERTION

    def __post_init__(self):
        if self.subject is not None:
            object.__setattr__(
                self, "subject", _as_story_reference(self.subject)
            )
        if self.object_reference is not None:
            object.__setattr__(
                self,
                "object_reference",
                _as_story_reference(self.object_reference),
            )

    def evaluate(self, engine):
        states = {
            CanonState(value) for value in self.canon_states
        }
        sources = set(self.source_document_ids)
        required_qualifiers = dict(self.qualifiers)
        results = []
        for assertion in engine.assertions.assertions:
            if self.subject is not None and assertion.subject != self.subject:
                continue
            if self.predicate and assertion.predicate != self.predicate:
                continue
            if self.object_reference is not None and (
                assertion.object.kind is not AssertionTermKind.REFERENCE
                or assertion.object.reference != self.object_reference
            ):
                continue
            if states and assertion.canon_state not in states:
                continue
            if sources and assertion.provenance.document_id not in sources:
                continue
            actual_qualifiers = {
                item.name: item.value for item in assertion.qualifiers
            }
            if any(
                actual_qualifiers.get(name) != value
                for name, value in required_qualifiers.items()
            ):
                continue
            results.append(QueryResult(QueryScope.ASSERTION, assertion.id))
        return frozenset(results)


@dataclass(frozen=True)
class DocumentsReferencing(QueryExpression):
    target_ids: Tuple[str, ...]
    require_all: bool = True

    @property
    def scope(self):
        return QueryScope.DOCUMENT

    def evaluate(self, engine):
        required = set(self.target_ids)
        found = {}
        for occurrence in engine.references.references:
            if occurrence.resolved_target_id in required:
                found.setdefault(
                    occurrence.source_document_id, set()
                ).add(occurrence.resolved_target_id)
        return frozenset(
            QueryResult(QueryScope.DOCUMENT, document_id)
            for document_id, targets in found.items()
            if (
                targets == required
                if self.require_all
                else bool(targets.intersection(required))
            )
        )


@dataclass(frozen=True)
class EntitiesWhere(QueryExpression):
    entity_type: str = ""
    surface: str = ""

    @property
    def scope(self):
        return QueryScope.ENTITY

    def evaluate(self, engine):
        exact_ids = {
            item.id for item in engine.entities.exact_matches(self.surface)
        } if self.surface else set()
        return frozenset(
            QueryResult(QueryScope.ENTITY, entity.id)
            for entity in engine.entities.entities
            if (not self.entity_type or entity.type == self.entity_type)
            and (not self.surface or entity.id in exact_ids)
        )


@dataclass(frozen=True)
class EntitiesRelatedTo(QueryExpression):
    target: StoryReference
    predicate: str = ""
    direction: str = "either"

    @property
    def scope(self):
        return QueryScope.ENTITY

    def __post_init__(self):
        object.__setattr__(
            self, "target", _as_story_reference(self.target)
        )
        if self.direction not in ("incoming", "outgoing", "either"):
            raise ValueError("Relationship direction is invalid.")

    def evaluate(self, engine):
        identifiers = set()
        for assertion in engine.assertions.relationships(self.predicate):
            other = assertion.object.reference
            if (
                self.direction in ("outgoing", "either")
                and assertion.subject == self.target
                and other.kind == "entity"
            ):
                identifiers.add(other.id)
            if (
                self.direction in ("incoming", "either")
                and other == self.target
                and assertion.subject.kind == "entity"
            ):
                identifiers.add(assertion.subject.id)
        return frozenset(
            QueryResult(QueryScope.ENTITY, identifier)
            for identifier in identifiers
        )


@dataclass(frozen=True)
class And(QueryExpression):
    expressions: Tuple[QueryExpression, ...]
    scope: QueryScope = field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self, "scope", _common_scope(self.expressions)
        )

    def evaluate(self, engine):
        if not self.expressions:
            return frozenset()
        result = self.expressions[0].evaluate(engine)
        for expression in self.expressions[1:]:
            result = result.intersection(expression.evaluate(engine))
        return result


@dataclass(frozen=True)
class Or(QueryExpression):
    expressions: Tuple[QueryExpression, ...]
    scope: QueryScope = field(init=False)

    def __post_init__(self):
        object.__setattr__(
            self, "scope", _common_scope(self.expressions)
        )

    def evaluate(self, engine):
        result = frozenset()
        for expression in self.expressions:
            result = result.union(expression.evaluate(engine))
        return result


@dataclass(frozen=True)
class Not(QueryExpression):
    scope: QueryScope
    expression: QueryExpression

    def __post_init__(self):
        scope = QueryScope(self.scope)
        if QueryScope(self.expression.scope) is not scope:
            raise ValueError("Not expression scope must match its universe.")
        object.__setattr__(self, "scope", scope)

    def evaluate(self, engine):
        return engine.universe(self.scope).difference(
            self.expression.evaluate(engine)
        )


class StoryQueryEngine:
    """Evaluate typed query nodes without exposing storage implementation."""

    def __init__(self, entities, references, assertions):
        self.entities = entities
        self.references = references
        self.assertions = assertions

    def execute(self, expression: QueryExpression) -> Tuple[QueryResult, ...]:
        return tuple(sorted(expression.evaluate(self)))

    def universe(self, scope):
        scope = QueryScope(scope)
        if scope is QueryScope.ENTITY:
            identifiers = (item.id for item in self.entities.entities)
        elif scope is QueryScope.DOCUMENT:
            identifiers = (item.id for item in self.references.documents)
        else:
            identifiers = (item.id for item in self.assertions.assertions)
        return frozenset(QueryResult(scope, value) for value in identifiers)


def _as_story_reference(value):
    if isinstance(value, StoryReference):
        return value
    try:
        return StoryReference(str(value.kind), str(value.id))
    except AttributeError as error:
        raise TypeError(
            "Query references require kind and id attributes."
        ) from error


def _common_scope(expressions):
    if not expressions:
        raise ValueError("Boolean queries require at least one expression.")
    scopes = {QueryScope(expression.scope) for expression in expressions}
    if len(scopes) != 1:
        raise ValueError("Boolean query expressions must share one scope.")
    return scopes.pop()
