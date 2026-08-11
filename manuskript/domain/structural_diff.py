"""Deterministic project-aware diffs over canonical project snapshots."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum

from manuskript.domain.assertion_dsl import assertions_from_source
from manuskript.domain.markdown_dsl import MarkdownDslParser


class StructuralChangeKind(str, Enum):
    DOCUMENT_ADDED = "document-added"
    DOCUMENT_DELETED = "document-deleted"
    DOCUMENT_MOVED = "document-moved"
    DOCUMENT_RENAMED = "document-renamed"
    DOCUMENT_METADATA = "document-metadata-changed"
    PARAGRAPHS_CHANGED = "paragraphs-changed"
    ENTITY_ADDED = "entity-added"
    ENTITY_DELETED = "entity-deleted"
    ENTITY_RENAMED = "entity-renamed"
    REFERENCE_ADDED = "reference-added"
    REFERENCE_DELETED = "reference-deleted"
    ASSERTION_ADDED = "assertion-added"
    ASSERTION_DELETED = "assertion-deleted"
    ASSERTION_CHANGED = "assertion-changed"


@dataclass(frozen=True)
class StructuralChange:
    kind: StructuralChangeKind
    subject_id: str
    summary: str
    before: str = ""
    after: str = ""


@dataclass(frozen=True)
class StructuralDiffReport:
    changes: tuple[StructuralChange, ...]

    @property
    def empty(self):
        return not self.changes

    def render_text(self):
        if not self.changes:
            return "No structural changes."
        return "\n".join(
            "{}: {}".format(item.kind.value, item.summary)
            for item in self.changes
        )


class CanonicalProjectDiffer:
    def compare(self, before, after):
        before_documents = {
            item.id: item for item in before.documents()
        }
        after_documents = {
            item.id: item for item in after.documents()
        }
        before_entities = {item.id: item for item in before.entities}
        after_entities = {item.id: item for item in after.entities}
        before_positions = _positions(before)
        after_positions = _positions(after)
        changes = []

        for identifier in sorted(before_documents.keys() - after_documents.keys()):
            if identifier in before_entities:
                continue
            item = before_documents[identifier]
            changes.append(StructuralChange(
                StructuralChangeKind.DOCUMENT_DELETED,
                identifier,
                "Deleted document {!r}.".format(item.title),
                item.title,
                "",
            ))
        for identifier in sorted(after_documents.keys() - before_documents.keys()):
            if identifier in after_entities:
                continue
            item = after_documents[identifier]
            changes.append(StructuralChange(
                StructuralChangeKind.DOCUMENT_ADDED,
                identifier,
                "Added document {!r}.".format(item.title),
                "",
                item.title,
            ))
        for identifier in sorted(before_documents.keys() & after_documents.keys()):
            previous = before_documents[identifier]
            current = after_documents[identifier]
            if (
                previous.title != current.title
                and identifier not in before_entities
                and identifier not in after_entities
            ):
                changes.append(StructuralChange(
                    StructuralChangeKind.DOCUMENT_RENAMED,
                    identifier,
                    "Renamed {!r} to {!r}.".format(
                        previous.title, current.title
                    ),
                    previous.title,
                    current.title,
                ))
            if before_positions.get(identifier) != after_positions.get(identifier):
                changes.append(StructuralChange(
                    StructuralChangeKind.DOCUMENT_MOVED,
                    identifier,
                    "Moved {!r} in the project structure.".format(
                        current.title
                    ),
                    _position_text(before_positions.get(identifier)),
                    _position_text(after_positions.get(identifier)),
                ))
            before_metadata = (
                previous.metadata, previous.structured_metadata
            )
            after_metadata = (
                current.metadata, current.structured_metadata
            )
            if before_metadata != after_metadata:
                changes.append(StructuralChange(
                    StructuralChangeKind.DOCUMENT_METADATA,
                    identifier,
                    "Changed metadata for {!r}.".format(current.title),
                ))
            if previous.text != current.text:
                changes.extend(_text_changes(identifier, previous, current))

        changes.extend(_entity_changes(before_entities, after_entities))
        return StructuralDiffReport(tuple(sorted(
            changes,
            key=lambda item: (item.kind.value, item.subject_id, item.summary),
        )))


def _positions(project):
    found = {}

    def collect(documents, parent=""):
        for index, document in enumerate(documents):
            found[document.id] = (parent, index, document.source_path)
            collect(document.children, document.id)

    collect(project.outline)
    for index, entity in enumerate(project.entities):
        found[entity.id] = ("entities", index, entity.document.source_path)
    return found


def _position_text(value):
    if value is None:
        return ""
    return "parent={}, index={}, path={}".format(*value)


def _text_changes(identifier, before, after):
    changes = []
    before_assertions, _ = assertions_from_source(before.text)
    after_assertions, _ = assertions_from_source(after.text)
    before_by_id = {item.id: item for item in before_assertions}
    after_by_id = {item.id: item for item in after_assertions}
    for assertion_id in sorted(before_by_id.keys() - after_by_id.keys()):
        changes.append(StructuralChange(
            StructuralChangeKind.ASSERTION_DELETED,
            assertion_id,
            "Deleted assertion {} from {!r}.".format(
                assertion_id, after.title
            ),
        ))
    for assertion_id in sorted(after_by_id.keys() - before_by_id.keys()):
        changes.append(StructuralChange(
            StructuralChangeKind.ASSERTION_ADDED,
            assertion_id,
            "Added assertion {} to {!r}.".format(
                assertion_id, after.title
            ),
        ))
    for assertion_id in sorted(before_by_id.keys() & after_by_id.keys()):
        if before_by_id[assertion_id] != after_by_id[assertion_id]:
            changes.append(StructuralChange(
                StructuralChangeKind.ASSERTION_CHANGED,
                assertion_id,
                "Changed assertion {} in {!r}.".format(
                    assertion_id, after.title
                ),
            ))

    before_references = _reference_counter(before.text)
    after_references = _reference_counter(after.text)
    for reference, count in sorted((after_references - before_references).items()):
        changes.append(StructuralChange(
            StructuralChangeKind.REFERENCE_ADDED,
            identifier,
            "Added {} reference(s) to {!r} in {!r}.".format(
                count, reference, after.title
            ),
        ))
    for reference, count in sorted((before_references - after_references).items()):
        changes.append(StructuralChange(
            StructuralChangeKind.REFERENCE_DELETED,
            identifier,
            "Deleted {} reference(s) to {!r} from {!r}.".format(
                count, reference, after.title
            ),
        ))

    before_paragraphs = _paragraphs(before.text)
    after_paragraphs = _paragraphs(after.text)
    matcher = SequenceMatcher(None, before_paragraphs, after_paragraphs)
    changed = sum(
        max(before_end - before_start, after_end - after_start)
        for operation, before_start, before_end, after_start, after_end
        in matcher.get_opcodes()
        if operation != "equal"
    )
    if changed:
        changes.append(StructuralChange(
            StructuralChangeKind.PARAGRAPHS_CHANGED,
            identifier,
            "Changed {} paragraph block(s) in {!r}.".format(
                changed, after.title
            ),
            str(len(before_paragraphs)),
            str(len(after_paragraphs)),
        ))
    return changes


def _reference_counter(text):
    from collections import Counter
    return Counter(
        (link.target, link.display or "")
        for link in MarkdownDslParser().parse(text).wikilinks
    )


def _paragraphs(text):
    return tuple(
        value.strip() for value in text.replace("\r\n", "\n").split("\n\n")
        if value.strip()
    )


def _entity_changes(before, after):
    changes = []
    for identifier in sorted(before.keys() - after.keys()):
        changes.append(StructuralChange(
            StructuralChangeKind.ENTITY_DELETED,
            identifier,
            "Deleted entity {!r}.".format(before[identifier].title),
        ))
    for identifier in sorted(after.keys() - before.keys()):
        changes.append(StructuralChange(
            StructuralChangeKind.ENTITY_ADDED,
            identifier,
            "Added entity {!r}.".format(after[identifier].title),
        ))
    for identifier in sorted(before.keys() & after.keys()):
        if before[identifier].title != after[identifier].title:
            changes.append(StructuralChange(
                StructuralChangeKind.ENTITY_RENAMED,
                identifier,
                "Renamed entity {!r} to {!r}.".format(
                    before[identifier].title, after[identifier].title
                ),
                before[identifier].title,
                after[identifier].title,
            ))
    return changes
