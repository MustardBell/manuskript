"""Disposable project index of explicit source-owned story assertions."""

from dataclasses import dataclass
from typing import Iterable, Tuple

from manuskript.domain.assertion_dsl import (
    assertions_from_source,
    bind_assertion_to_document,
)
from manuskript.domain.markdown_dsl import DslDiagnostic, SourceSpan
from manuskript.domain.story_assertions import AssertionTermKind


@dataclass(frozen=True)
class AssertionDocument:
    id: str
    path: str
    text: str


@dataclass(frozen=True)
class AssertionStoreIssue:
    document_id: str
    path: str
    message: str
    severity: str
    source_span: SourceSpan


class AssertionStore:
    """Rebuildable assertion state; Markdown documents remain authority."""

    def __init__(self):
        self._documents = {}
        self._assertions = ()
        self._issues = ()

    @property
    def assertions(self):
        return self._assertions

    @property
    def issues(self):
        return self._issues

    @property
    def documents(self) -> Tuple[AssertionDocument, ...]:
        return tuple(self._documents.values())

    def rebuild(self, documents: Iterable[AssertionDocument], entity_ids=()):
        self._documents = {document.id: document for document in documents}
        assertions = []
        issues = []
        identifiers = set()
        for document in self._documents.values():
            parsed, diagnostics = assertions_from_source(document.text)
            issues.extend(
                self._issue(document, diagnostic)
                for diagnostic in diagnostics
            )
            for assertion in parsed:
                bound = bind_assertion_to_document(assertion, document.id)
                if bound.id in identifiers:
                    issues.append(AssertionStoreIssue(
                        document.id,
                        document.path,
                        "Duplicate assertion ID: {}".format(bound.id),
                        "error",
                        bound.provenance.source_span or SourceSpan(0, 0),
                    ))
                    continue
                identifiers.add(bound.id)
                assertions.append(bound)
        self._assertions = tuple(assertions)
        self._issues = tuple(issues) + self._reference_issues(
            set(entity_ids), set(self._documents), identifiers
        )
        return self._assertions

    def update(self, document: AssertionDocument, entity_ids=()):
        self._documents[document.id] = document
        return self.rebuild(self._documents.values(), entity_ids)

    def find(self, assertion_id):
        return next(
            (item for item in self._assertions if item.id == assertion_id),
            None,
        )

    def by_subject(self, subject):
        return tuple(
            item for item in self._assertions if item.subject == subject
        )

    def relationships(self, predicate=""):
        return tuple(
            item for item in self._assertions
            if item.object.kind is AssertionTermKind.REFERENCE
            and (not predicate or item.predicate == predicate)
        )

    @staticmethod
    def _issue(document, diagnostic: DslDiagnostic):
        return AssertionStoreIssue(
            document.id,
            document.path,
            diagnostic.message,
            diagnostic.severity,
            diagnostic.span,
        )

    def _reference_issues(self, entity_ids, document_ids, assertion_ids):
        known = {
            "entity": entity_ids,
            "document": document_ids,
            "assertion": assertion_ids,
        }
        issues = []
        for assertion in self._assertions:
            references = [assertion.subject]
            if assertion.object.reference is not None:
                references.append(assertion.object.reference)
            if assertion.validity is not None:
                references.extend(
                    point.reference
                    for point in (
                        assertion.validity.valid_from,
                        assertion.validity.valid_until,
                    )
                    if point is not None and point.reference is not None
                )
            for reference in references:
                valid_ids = known.get(reference.kind)
                if valid_ids is None or reference.id in valid_ids:
                    continue
                issues.append(AssertionStoreIssue(
                    assertion.provenance.document_id,
                    self._documents[
                        assertion.provenance.document_id
                    ].path,
                    "Missing {} reference: {}".format(
                        reference.kind, reference.id
                    ),
                    "warning",
                    assertion.provenance.source_span or SourceSpan(0, 0),
                ))
        return tuple(issues)
