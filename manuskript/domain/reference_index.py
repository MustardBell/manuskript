"""Disposable deterministic index of explicit Markdown wikilinks."""

import posixpath
import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple

from manuskript.domain.markdown_dsl import (
    MarkdownDslParser,
    SourceSpan,
)


class ReferenceResolution(Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"
    EXTERNAL = "external"


@dataclass(frozen=True)
class ReferenceDocument:
    id: str
    path: str
    title: str
    text: str
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceOccurrence:
    source_document_id: str
    source_path: str
    source_span: SourceSpan
    target_span: SourceSpan
    raw_target: str
    display_text: Optional[str]
    resolution: ReferenceResolution
    resolved_target_id: Optional[str] = None
    resolved_target_path: Optional[str] = None


@dataclass(frozen=True)
class ReferenceRefactor:
    target_document_id: str
    old_path: str
    new_path: str
    updated_sources: Mapping[str, str]


@dataclass(frozen=True)
class ReferenceSuggestion:
    document_id: str
    target: str
    title: str
    path: str


class ReferenceIndex:
    """Rebuildable reference state; source documents remain authoritative."""

    _EXTERNAL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

    def __init__(self, parser=None):
        self._parser = parser or MarkdownDslParser()
        self._documents: Dict[str, ReferenceDocument] = {}
        self._references: Tuple[ReferenceOccurrence, ...] = ()

    @property
    def references(self) -> Tuple[ReferenceOccurrence, ...]:
        return self._references

    @property
    def documents(self) -> Tuple[ReferenceDocument, ...]:
        return tuple(self._documents.values())

    def rebuild(
        self, documents: Iterable[ReferenceDocument]
    ) -> Tuple[ReferenceOccurrence, ...]:
        self._documents = {document.id: document for document in documents}
        addresses = self._addresses(self._documents.values())
        references = []
        for document in self._documents.values():
            tree = self._parser.parse(document.text)
            for link in tree.wikilinks:
                resolution, target = self._resolve(link.target, addresses)
                references.append(ReferenceOccurrence(
                    source_document_id=document.id,
                    source_path=document.path,
                    source_span=link.span,
                    target_span=link.target_span,
                    raw_target=link.target,
                    display_text=link.display,
                    resolution=resolution,
                    resolved_target_id=target.id if target is not None else None,
                    resolved_target_path=(
                        target.path if target is not None else None
                    ),
                ))
        self._references = tuple(references)
        return self._references

    def update(self, document: ReferenceDocument) -> None:
        previous = self._documents.get(document.id)
        self._documents[document.id] = document
        if (
            previous is None
            or previous.path != document.path
            or previous.title != document.title
            or previous.aliases != document.aliases
        ):
            self.rebuild(self._documents.values())
            return
        addresses = self._addresses(self._documents.values())
        retained = [
            reference for reference in self._references
            if reference.source_document_id != document.id
        ]
        tree = self._parser.parse(document.text)
        updated = []
        for link in tree.wikilinks:
            resolution, target = self._resolve(link.target, addresses)
            updated.append(ReferenceOccurrence(
                source_document_id=document.id,
                source_path=document.path,
                source_span=link.span,
                target_span=link.target_span,
                raw_target=link.target,
                display_text=link.display,
                resolution=resolution,
                resolved_target_id=target.id if target is not None else None,
                resolved_target_path=target.path if target is not None else None,
            ))
        self._references = tuple(retained + updated)

    def remove(self, document_id: str) -> bool:
        if document_id not in self._documents:
            return False
        del self._documents[document_id]
        self.rebuild(self._documents.values())
        return True

    def backlinks(self, target_document_id: str) -> Tuple[ReferenceOccurrence, ...]:
        return tuple(
            reference for reference in self._references
            if reference.resolved_target_id == target_document_id
        )

    def broken(self) -> Tuple[ReferenceOccurrence, ...]:
        return tuple(
            reference for reference in self._references
            if reference.resolution in (
                ReferenceResolution.MISSING,
                ReferenceResolution.AMBIGUOUS,
            )
        )

    def resolve(
        self, raw_target: str
    ) -> Tuple[ReferenceResolution, Optional[ReferenceDocument]]:
        """Resolve a target through the same rules used by the index."""

        return self._resolve(
            raw_target, self._addresses(self._documents.values())
        )

    def complete(self, prefix: str) -> Tuple[ReferenceSuggestion, ...]:
        """Return deterministic path suggestions for a wikilink prefix."""

        normalized_prefix = (
            self._normalize(prefix) if prefix.strip() else ""
        )
        suggestions = []
        for document in self._documents.values():
            target = self._without_markdown_extension(document.path)
            searchable = {
                self._normalize(target),
                self._normalize(posixpath.basename(target)),
                self._normalize(document.title),
                *(self._normalize(alias) for alias in document.aliases),
            }
            if any(
                candidate.startswith(normalized_prefix)
                for candidate in searchable
            ):
                suggestions.append(ReferenceSuggestion(
                    document.id, target, document.title, document.path
                ))
        return tuple(sorted(
            suggestions,
            key=lambda item: (
                item.title.casefold(), item.target.casefold(), item.document_id
            ),
        ))

    def cooccurring(
        self, *target_document_ids: str
    ) -> Tuple[ReferenceDocument, ...]:
        required = set(target_document_ids)
        found = {}
        for reference in self._references:
            if reference.resolved_target_id in required:
                found.setdefault(reference.source_document_id, set()).add(
                    reference.resolved_target_id
                )
        return tuple(
            self._documents[document_id]
            for document_id, targets in found.items()
            if targets == required
        )

    def plan_path_refactor(
        self,
        target_document_id: str,
        new_path: str,
    ) -> ReferenceRefactor:
        target = self._documents[target_document_id]
        new_address = self._without_markdown_extension(new_path)
        edits: Dict[str, list] = {}
        for reference in self.backlinks(target_document_id):
            edits.setdefault(reference.source_document_id, []).append(
                (reference.target_span, new_address)
            )
        updated = {}
        for document_id, replacements in edits.items():
            document = self._documents[document_id]
            tree = self._parser.parse(document.text)
            updated[document_id] = tree.replace(replacements)
        return ReferenceRefactor(
            target_document_id=target_document_id,
            old_path=target.path,
            new_path=new_path,
            updated_sources=updated,
        )

    @classmethod
    def _addresses(
        cls, documents: Iterable[ReferenceDocument]
    ) -> Dict[str, Tuple[ReferenceDocument, ...]]:
        addresses: Dict[str, list] = {}
        for document in documents:
            path = cls._without_markdown_extension(document.path)
            candidates = {
                path,
                posixpath.basename(path),
                document.title,
                *document.aliases,
            }
            for candidate in candidates:
                normalized = cls._normalize(candidate)
                addresses.setdefault(normalized, []).append(document)
        return {
            address: tuple({item.id: item for item in values}.values())
            for address, values in addresses.items()
        }

    def _resolve(self, raw_target, addresses):
        if self._EXTERNAL.match(raw_target):
            return ReferenceResolution.EXTERNAL, None
        # Heading and block fragments select content inside the same target
        # document; document identity is resolved from the part before them.
        document_target = re.split(r"[#^]", raw_target, maxsplit=1)[0]
        candidates = addresses.get(self._normalize(document_target), ())
        if len(candidates) == 1:
            return ReferenceResolution.RESOLVED, candidates[0]
        if len(candidates) > 1:
            return ReferenceResolution.AMBIGUOUS, None
        return ReferenceResolution.MISSING, None

    @staticmethod
    def _normalize(value: str) -> str:
        return posixpath.normpath(
            value.strip().replace("\\", "/")
        ).casefold()

    @staticmethod
    def _without_markdown_extension(path: str) -> str:
        normalized = path.replace("\\", "/")
        return (
            normalized[:-3]
            if normalized.casefold().endswith(".md")
            else normalized
        )
