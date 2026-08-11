"""Read-only generic entity projections over legacy story models."""

import posixpath
from typing import Iterable, Tuple

from manuskript.domain.canonical_project import (
    CanonicalProject,
    EntityRecord,
    OutlineDocument,
    StructuredMetadataField,
)


class LegacyEntityAdapter:
    """Expose Character/World/Plot records without making them core types."""

    def project(self, project: CanonicalProject) -> Tuple[EntityRecord, ...]:
        entities = [
            self._character(record) for record in project.characters
        ]
        for record in project.world:
            entities.extend(self._world(record))
        entities.extend(self._plot(record) for record in project.plots)
        return tuple(entities)

    def _character(self, record):
        values = {item.name: item.value for item in record.fields}
        aliases = self._aliases(record.custom_fields)
        source_path = record.source_path or posixpath.join(
            "Legacy", "Characters", str(record.id) + ".md"
        )
        return EntityRecord(
            document=OutlineDocument(
                id=self._id("character", record.id),
                title=record.name,
                kind="entity",
                text=values.get("notes", ""),
                source_path=source_path,
            ),
            entity_type="character",
            aliases=aliases,
            metadata=self._metadata(
                record.fields + record.custom_fields,
                legacy_id=record.id,
            ),
        )

    def _world(self, record):
        values = {item.name: item.value for item in record.fields}
        identifier = values.get("ID", "")
        title = values.get("name", "Untitled world entity")
        current = EntityRecord(
            document=OutlineDocument(
                id=self._id("world", identifier or title),
                title=title,
                kind="entity",
                text=values.get("description", ""),
                source_path=posixpath.join(
                    "Legacy", "World", str(identifier or title) + ".md"
                ),
            ),
            entity_type="world",
            metadata=self._metadata(record.fields, legacy_id=identifier),
        )
        descendants = [current]
        for child in record.children:
            descendants.extend(self._world(child))
        return descendants

    def _plot(self, record):
        values = {item.name: item.value for item in record.fields}
        identifier = values.get("ID", "")
        title = values.get("name", "Untitled plot")
        return EntityRecord(
            document=OutlineDocument(
                id=self._id("plot", identifier or title),
                title=title,
                kind="entity",
                text=values.get("description", values.get("summary", "")),
                source_path=posixpath.join(
                    "Legacy", "Plots", str(identifier or title) + ".md"
                ),
            ),
            entity_type="plot",
            metadata=self._metadata(record.fields, legacy_id=identifier),
        )

    @staticmethod
    def _aliases(fields: Iterable) -> Tuple[str, ...]:
        aliases = []
        seen = set()
        for field in fields:
            if field.name.casefold() not in ("alias", "aliases"):
                continue
            for value in str(field.value).splitlines():
                value = " ".join(value.split())
                key = value.casefold()
                if value and key not in seen:
                    aliases.append(value)
                    seen.add(key)
        return tuple(aliases)

    @staticmethod
    def _metadata(fields: Iterable, legacy_id=""):
        metadata = [
            StructuredMetadataField(item.name, item.value) for item in fields
        ]
        metadata.append(StructuredMetadataField("legacy-id", str(legacy_id)))
        return tuple(metadata)

    @staticmethod
    def _id(kind, identifier):
        return "legacy:{}:{}".format(kind, identifier)
