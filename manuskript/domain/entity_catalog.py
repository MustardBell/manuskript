"""Generic entity identities and deterministic reference choices."""

import posixpath
import re
import uuid
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Optional, Tuple

from manuskript.domain.canonical_project import (
    EntityRecord,
    OutlineDocument,
    StructuredMetadataField,
)
from manuskript.domain.markdown_dsl import MarkdownDslParser, SourceSpan
from manuskript.domain.morphology import MorphologyIndex
from manuskript.domain.project_paths import normalize_project_path


@dataclass(frozen=True)
class EntitySchema:
    type: str
    label: str
    directory: str


@dataclass(frozen=True)
class EntityReferenceChoice:
    entity_id: str
    entity_type: str
    title: str
    target: str
    aliases: Tuple[str, ...] = ()
    exact_match: bool = False


@dataclass(frozen=True)
class EntitySurfaceMatch:
    span: SourceSpan
    surface: str
    entity_ids: Tuple[str, ...]

    @property
    def is_unique(self) -> bool:
        return len(self.entity_ids) == 1

    @property
    def is_ambiguous(self) -> bool:
        return len(self.entity_ids) > 1


class EntitySchemaRegistry:
    """Extensible naming/path policy; entities themselves remain generic."""

    def __init__(self, schemas=()):
        self._schemas = {}
        for schema in schemas:
            self.register(schema)

    @property
    def schemas(self) -> Tuple[EntitySchema, ...]:
        return tuple(self._schemas.values())

    def register(self, schema: EntitySchema) -> None:
        if not schema.type or not schema.label or not schema.directory:
            raise ValueError("Entity schemas require type, label, and directory.")
        raw_directory = schema.directory.replace("\\", "/")
        try:
            directory = normalize_project_path(raw_directory)
        except ValueError as error:
            raise ValueError(
                "Entity schema directories must be safe relative paths."
            ) from error
        if directory != raw_directory:
            raise ValueError("Entity schema directories must be safe relative paths.")
        self._schemas[schema.type] = replace(schema, directory=directory)

    def get(self, entity_type: str) -> Optional[EntitySchema]:
        return self._schemas.get(str(entity_type))


def first_party_story_entity_schemas() -> EntitySchemaRegistry:
    """Return optional story schemas without teaching core link syntax fiction."""

    return EntitySchemaRegistry((
        EntitySchema("project", "Project", "Project"),
        EntitySchema("character", "Character", "Characters"),
        EntitySchema("place", "Place", "Places"),
        EntitySchema("object", "Object", "Objects"),
        EntitySchema("organization", "Organization", "Organizations"),
        EntitySchema("concept", "Concept", "Concepts"),
        EntitySchema("event", "Event", "Events"),
        EntitySchema("plot", "Plot", "Plots"),
        EntitySchema("world", "World item", "World"),
        EntitySchema("entity", "Other", "Entities"),
    ))


class EntityCatalog:
    """Mutable, project-scoped catalog rebuilt from authoritative documents."""

    def __init__(
        self,
        schemas=None,
        id_factory: Optional[Callable[[], str]] = None,
        morphology_index: Optional[MorphologyIndex] = None,
    ):
        self.schemas = schemas or EntitySchemaRegistry()
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))
        self.morphology_index = morphology_index
        self._native = ()
        self._legacy = ()
        self._writable = False
        self._listeners = []

    @property
    def writable(self) -> bool:
        return self._writable

    @property
    def entities(self) -> Tuple[EntityRecord, ...]:
        return self._native + self._legacy

    @property
    def native_entities(self) -> Tuple[EntityRecord, ...]:
        return self._native

    def replace(
        self,
        native: Iterable[EntityRecord],
        legacy: Iterable[EntityRecord] = (),
        *,
        writable: bool = False,
    ) -> None:
        native = tuple(native)
        legacy = tuple(legacy)
        self._validate(native)
        self._native = native
        self._legacy = legacy
        self._writable = bool(writable)
        self._rebuild_morphology()
        self._notify()

    def subscribe(self, listener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    def unsubscribe(self, listener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def find(self, entity_id: str) -> Optional[EntityRecord]:
        return next(
            (entity for entity in self.entities if entity.id == entity_id),
            None,
        )

    def exact_matches(self, surface: str) -> Tuple[EntityRecord, ...]:
        normalized = self._normalize_surface(surface)
        if not normalized:
            return ()
        if self.morphology_index is not None:
            identifiers = {
                item.entity_id
                for item in self.morphology_index.lookup(surface)
            }
            return tuple(
                entity for entity in self.entities
                if entity.id in identifiers
            )
        return tuple(
            entity for entity in self.entities
            if normalized in {
                self._normalize_surface(entity.title),
                *(self._normalize_surface(alias) for alias in entity.aliases),
            }
        )

    def reference_choices(
        self, surface: str = ""
    ) -> Tuple[EntityReferenceChoice, ...]:
        exact_ids = {entity.id for entity in self.exact_matches(surface)}
        choices = [
            self.reference_choice(entity, entity.id in exact_ids)
            for entity in self.entities
        ]
        return tuple(sorted(
            choices,
            key=lambda item: (
                not item.exact_match,
                item.entity_type.casefold(),
                item.title.casefold(),
                item.entity_id,
            ),
        ))

    def reference_choice(
        self, entity: EntityRecord, exact_match: bool = False
    ) -> EntityReferenceChoice:
        return EntityReferenceChoice(
            entity.id,
            entity.type,
            entity.title,
            self.reference_target(entity),
            entity.aliases,
            exact_match,
        )

    def scan(self, source: str) -> Tuple[EntitySurfaceMatch, ...]:
        """Find explicit title/alias surfaces without inferring semantics."""

        parser = MarkdownDslParser()
        tree = parser.parse(source)
        excluded = tuple(
            parser.excluded_spans(source)
        ) + tuple(link.span for link in tree.wikilinks)
        surfaces = {}
        for entity in self.entities:
            for value in self.surface_forms(entity.id):
                key = self._normalize_surface(value)
                if key:
                    surfaces.setdefault(key, (value, []))[1].append(entity.id)

        candidates = []
        for _key, (surface, entity_ids) in surfaces.items():
            pattern = re.compile(
                r"(?<!\w){}(?!\w)".format(re.escape(surface)),
                re.IGNORECASE | re.UNICODE,
            )
            for match in pattern.finditer(source):
                span = SourceSpan(match.start(), match.end())
                if any(
                    area.start < span.end and span.start < area.end
                    for area in excluded
                ):
                    continue
                candidates.append(EntitySurfaceMatch(
                    span,
                    match.group(0),
                    tuple(sorted(set(entity_ids))),
                ))

        # Prefer the longest deterministic match at a position, so "Mara
        # Vale" is not also reported as the shorter "Mara".
        candidates.sort(key=lambda item: (
            item.span.start, -item.span.length, item.surface.casefold()
        ))
        accepted = []
        for candidate in candidates:
            if accepted and candidate.span.start < accepted[-1].span.end:
                continue
            accepted.append(candidate)
        return tuple(accepted)

    def create(
        self,
        entity_type: str,
        title: str,
        aliases=(),
        metadata: Iterable[StructuredMetadataField] = (),
    ) -> EntityRecord:
        if not self._writable:
            raise PermissionError(
                "Native entities require a writable Format 2 project."
            )
        title = " ".join(str(title).split())
        if not title:
            raise ValueError("An entity title may not be empty.")
        schema = self.schemas.get(entity_type)
        if schema is None:
            schema = self.schemas.get("entity") or EntitySchema(
                str(entity_type) or "entity", "Other", "Entities"
            )
        entity_id = str(self._id_factory())
        if self.find(entity_id) is not None:
            raise ValueError("The entity ID already exists: {}".format(entity_id))
        path = self._available_path(schema.directory, title)
        entity = EntityRecord(
            document=OutlineDocument(
                id=entity_id,
                title=title,
                kind="entity",
                text="",
                source_path=path,
                source_format="yaml-frontmatter",
            ),
            entity_type=schema.type,
            aliases=self._unique_aliases(aliases, title),
            metadata=tuple(metadata),
        )
        self._native = self._native + (entity,)
        self._rebuild_morphology()
        self._notify()
        return entity

    def update(
        self,
        entity_id: str,
        *,
        title: Optional[str] = None,
        entity_type: Optional[str] = None,
        aliases=None,
        text: Optional[str] = None,
        metadata: Optional[Iterable[StructuredMetadataField]] = None,
    ) -> EntityRecord:
        if not self._writable:
            raise PermissionError(
                "Native entities require a writable Format 2 project."
            )
        entity = next(
            (item for item in self._native if item.id == entity_id), None
        )
        if entity is None:
            raise KeyError(entity_id)
        new_title = (
            " ".join(str(title).split()) if title is not None else entity.title
        )
        if not new_title:
            raise ValueError("An entity title may not be empty.")
        new_type = (
            entity.type if entity_type is None else str(entity_type).strip()
        )
        if not new_type:
            raise ValueError("An entity type may not be empty.")
        updated = replace(
            entity,
            document=replace(
                entity.document,
                title=new_title,
                text=entity.document.text if text is None else str(text),
            ),
            entity_type=new_type,
            aliases=(
                entity.aliases
                if aliases is None
                else self._unique_aliases(aliases, new_title)
            ),
            metadata=(
                entity.metadata if metadata is None else tuple(metadata)
            ),
        )
        self._native = tuple(
            updated if item.id == entity_id else item for item in self._native
        )
        self._rebuild_morphology()
        self._notify()
        return updated

    def delete(self, entity_id: str) -> EntityRecord:
        if not self._writable:
            raise PermissionError(
                "Native entities require a writable project."
            )
        entity = next(
            (item for item in self._native if item.id == entity_id), None
        )
        if entity is None:
            raise KeyError(entity_id)
        self._native = tuple(
            item for item in self._native if item.id != entity_id
        )
        self._rebuild_morphology()
        self._notify()
        return entity

    def surface_forms(self, entity_id: str) -> Tuple[str, ...]:
        entity = self.find(entity_id)
        if entity is None:
            return ()
        if self.morphology_index is None:
            return (entity.title,) + entity.aliases
        return tuple(
            item.text for item in self.morphology_index.forms_for(entity_id)
        )

    def _rebuild_morphology(self):
        if self.morphology_index is not None:
            self.morphology_index.rebuild(self.entities)

    def refresh_derived_surfaces(self):
        self._rebuild_morphology()
        self._notify()

    def _notify(self):
        for listener in tuple(self._listeners):
            listener()

    @staticmethod
    def reference_target(entity: EntityRecord) -> str:
        path = entity.document.source_path.replace("\\", "/")
        return path[:-3] if path.casefold().endswith(".md") else path

    def _available_path(self, directory: str, title: str) -> str:
        slug = re.sub(
            r"[<>:\"/\\|?*\[\]\x00-\x1f]+", "-", title
        ).strip(" .") or "Entity"
        path = posixpath.join(directory, slug + ".md")
        used = {
            entity.document.source_path.casefold() for entity in self.entities
        }
        candidate = path
        duplicate = 2
        while candidate.casefold() in used:
            candidate = posixpath.join(
                directory, "{}-{}.md".format(slug, duplicate)
            )
            duplicate += 1
        return candidate

    @staticmethod
    def _normalize_surface(value: str) -> str:
        return " ".join(str(value).split()).casefold()

    @classmethod
    def _unique_aliases(cls, aliases, title):
        title_key = cls._normalize_surface(title)
        result = []
        seen = {title_key}
        for alias in aliases:
            alias = " ".join(str(alias).split())
            key = cls._normalize_surface(alias)
            if alias and key not in seen:
                result.append(alias)
                seen.add(key)
        return tuple(result)

    @staticmethod
    def _validate(entities):
        ids = set()
        paths = set()
        for entity in entities:
            if not entity.id or entity.id in ids:
                raise ValueError("Native entity IDs must be present and unique.")
            path = entity.document.source_path.casefold()
            if not path or path in paths:
                raise ValueError("Native entity paths must be present and unique.")
            ids.add(entity.id)
            paths.add(path)
