"""Canonical entity projections over legacy story-model records."""

import json
import posixpath
from typing import Iterable, Tuple

from manuskript.domain.canonical_project import (
    CanonicalProject,
    EntityRecord,
    OutlineDocument,
    StructuredMetadataField,
)


class LegacyEntityAdapter:
    """Expose legacy summary/story records through the entity vocabulary."""

    def project(self, project: CanonicalProject) -> Tuple[EntityRecord, ...]:
        entities = [self._project_summary(project)]
        entities.extend(
            self._character(record) for record in project.characters
        )
        for record in project.world:
            entities.extend(self._world(record, parent_id=""))
        entities.extend(self._plot(record) for record in project.plots)
        return tuple(entities)

    def _project_summary(self, project):
        metadata = tuple(
            StructuredMetadataField("project." + item.name, item.value)
            for item in project.metadata
        ) + tuple(
            StructuredMetadataField("summary." + item.name, item.value)
            for item in project.summary
            if item.name.casefold() != "full"
        )
        title = next(
            (
                item.value for item in project.metadata
                if item.name.casefold() == "title" and item.value.strip()
            ),
            "Project summary",
        )
        body = next(
            (
                item.value for item in project.summary
                if item.name.casefold() == "full"
            ),
            "",
        )
        return EntityRecord(
            document=OutlineDocument(
                id="legacy:project:summary",
                title=title,
                kind="entity",
                text=body,
                source_path="Project/Summary.md",
            ),
            entity_type="project",
            metadata=metadata,
        )

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
            ) + (
                StructuredMetadataField("legacy.color", record.color),
            ),
        )

    def _world(self, record, parent_id):
        values = {item.name: item.value for item in record.fields}
        identifier = values.get("ID", "")
        title = values.get("name", "Untitled world entity")
        stable_id = self._id("world", identifier or title)
        metadata = self._metadata(record.fields, legacy_id=identifier)
        if parent_id:
            metadata = metadata + (
                StructuredMetadataField("legacy.parent", parent_id),
            )
        current = EntityRecord(
            document=OutlineDocument(
                id=stable_id,
                title=title,
                kind="entity",
                text=values.get("description", ""),
                source_path=posixpath.join(
                    "Legacy", "World", str(identifier or title) + ".md"
                ),
            ),
            entity_type="world",
            metadata=metadata,
        )
        descendants = [current]
        for child in record.children:
            descendants.extend(self._world(child, parent_id=stable_id))
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
            metadata=self._metadata(record.fields, legacy_id=identifier) + (
                StructuredMetadataField(
                    "legacy.character_ids", list(record.character_ids)
                ),
                StructuredMetadataField(
                    "legacy.steps",
                    [
                        {
                            item.name: item.value
                            for item in step.fields
                        }
                        for step in record.steps
                    ],
                ),
            ),
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
        metadata = []
        for item in fields:
            if item.name.casefold() in ("alias", "aliases"):
                continue
            value = item.value
            if item.name.casefold() == "morphology":
                try:
                    decoded = json.loads(value)
                except (TypeError, ValueError):
                    decoded = None
                if isinstance(decoded, dict):
                    value = decoded
            metadata.append(StructuredMetadataField(item.name, value))
        metadata.append(
            StructuredMetadataField("legacy.id", str(legacy_id))
        )
        return tuple(metadata)

    @staticmethod
    def _id(kind, identifier):
        return "legacy:{}:{}".format(kind, identifier)
