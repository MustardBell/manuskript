"""Canonical entity projections over legacy story-model records."""

import json
import posixpath
from dataclasses import replace
from typing import Iterable, Tuple

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    EntityRecord,
    MetadataField,
    OutlineDocument,
    PlotRecord,
    StructuredMetadataField,
    WorldRecord,
)


CHARACTER_FIELD_NAMES = {
    "Name", "ID", "Importance", "POV", "Motivation", "Goal", "Conflict",
    "Epiphany", "Phrase Summary", "Paragraph Summary", "Full Summary",
    "Notes",
}
WORLD_FIELD_NAMES = {"name", "ID", "description", "passion", "conflict"}
PLOT_FIELD_NAMES = {
    "name", "ID", "importance", "description", "result", "summary",
}


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

    def update(
        self,
        project: CanonicalProject,
        entity: EntityRecord,
    ) -> CanonicalProject:
        """Write one projected entity back into its legacy canonical record.

        This adapter knows the old record vocabulary but not Qt.  Keeping the
        transformation here lets storage update both its canonical baseline
        and the live application model without making either representation
        authoritative over the other.
        """

        if entity.id == "project:summary":
            return self._update_summary(project, entity)
        if entity.id.startswith("legacy:character:"):
            identifier = self._legacy_identifier(entity)
            found = any(
                str(item.id) == identifier for item in project.characters
            )
            if not found:
                raise KeyError(entity.id)
            records = tuple(
                self._updated_character(item, entity)
                if str(item.id) == identifier else item
                for item in project.characters
            )
            return replace(project, characters=records)
        if entity.id.startswith("legacy:world:"):
            identifier = self._legacy_identifier(entity)
            records, found = self._update_world_records(
                project.world, identifier, entity
            )
            if not found:
                raise KeyError(entity.id)
            return replace(project, world=records)
        if entity.id.startswith("legacy:plot:"):
            identifier = self._legacy_identifier(entity)
            found = False
            records = []
            for item in project.plots:
                if str(item.value("ID") or item.value("name")) == identifier:
                    records.append(self._updated_plot(item, entity))
                    found = True
                else:
                    records.append(item)
            if not found:
                raise KeyError(entity.id)
            return replace(project, plots=tuple(records))
        raise KeyError(entity.id)

    def _update_summary(self, project, entity):
        values = {item.name: item.value for item in entity.metadata}
        metadata = self._replace_named_fields(
            project.metadata,
            {
                name: self._text(values.get("project." + name, ""))
                for name in {item.name for item in project.metadata}
                | {"Title"}
            },
        )
        metadata = self._replace_named_fields(
            metadata, {"Title": entity.title}
        )
        summary_names = {item.name for item in project.summary} | {"Full"}
        summary = self._replace_named_fields(
            project.summary,
            {
                name: (
                    entity.document.text if name == "Full"
                    else self._text(values.get("summary." + name, ""))
                )
                for name in summary_names
            },
        )
        return replace(project, metadata=metadata, summary=summary)

    def _updated_character(self, record, entity):
        values = self._editable_values(entity)
        standard = set(CHARACTER_FIELD_NAMES)
        values.update({
            "Name": entity.title,
            "ID": str(record.id),
            "Notes": entity.document.text,
        })
        fields = self._replace_named_fields(
            record.fields,
            {name: self._text(values.get(name, "")) for name in standard},
        )
        custom = [
            MetadataField(name, self._text(value))
            for name, value in values.items()
            if name.casefold() not in {
                item.casefold() for item in standard
            } and not name.startswith("legacy.")
        ]
        if entity.aliases:
            custom.append(MetadataField("Aliases", "\n".join(entity.aliases)))
        return replace(
            record,
            name=entity.title,
            fields=fields,
            custom_fields=tuple(custom),
        )

    def _update_world_records(self, records, identifier, entity):
        result = []
        found = False
        for record in records:
            record_id = str(record.value("ID") or record.value("name"))
            if record_id == identifier:
                result.append(self._updated_world(record, entity))
                found = True
                continue
            children, child_found = self._update_world_records(
                record.children, identifier, entity
            )
            result.append(
                replace(record, children=children) if child_found else record
            )
            found = found or child_found
        return tuple(result), found

    def _updated_world(self, record, entity):
        values = self._editable_values(entity)
        known = set(WORLD_FIELD_NAMES) | {item.name for item in record.fields}
        values.update({
            "ID": record.value("ID"),
            "name": entity.title,
            "description": entity.document.text,
        })
        return WorldRecord(
            self._replace_named_fields(
                record.fields,
                {name: self._text(values.get(name, "")) for name in known},
            ),
            record.children,
        )

    def _updated_plot(self, record, entity):
        values = self._editable_values(entity)
        known = set(PLOT_FIELD_NAMES) | {item.name for item in record.fields}
        values.update({
            "ID": record.value("ID"),
            "name": entity.title,
            "description": entity.document.text,
        })
        return PlotRecord(
            self._replace_named_fields(
                record.fields,
                {name: self._text(values.get(name, "")) for name in known},
            ),
            record.character_ids,
            record.steps,
        )

    @staticmethod
    def _editable_values(entity):
        return {
            item.name: item.value for item in entity.metadata
            if item.name not in (
                "legacy.id", "legacy.color", "legacy.parent",
                "legacy.character_ids", "legacy.steps",
            )
        }

    @staticmethod
    def _replace_named_fields(fields, values):
        by_key = {str(name).casefold(): (name, value) for name, value in values.items()}
        result = []
        emitted = set()
        for item in fields:
            key = item.name.casefold()
            if key in by_key:
                _name, value = by_key[key]
                if key not in emitted and value != "":
                    result.append(MetadataField(item.name, value))
                    emitted.add(key)
            else:
                result.append(item)
        for name, value in values.items():
            key = str(name).casefold()
            if key not in emitted and value != "":
                result.append(MetadataField(name, value))
                emitted.add(key)
        return tuple(result)

    @staticmethod
    def _legacy_identifier(entity):
        return entity.id.split(":", 2)[2]

    @staticmethod
    def _text(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _field_value(fields, name, default=""):
        expected = str(name).casefold()
        for item in reversed(tuple(fields)):
            if item.name.casefold() == expected:
                return item.value
        return default

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
                id="project:summary",
                title=title,
                kind="entity",
                text=body,
                source_path="Project/Summary.md",
            ),
            entity_type="project",
            metadata=metadata,
        )

    def _character(self, record):
        aliases = self._aliases(record.custom_fields)
        source_path = record.source_path or posixpath.join(
            "Legacy", "Characters", str(record.id) + ".md"
        )
        return EntityRecord(
            document=OutlineDocument(
                id=self._id("character", record.id),
                title=record.name,
                kind="entity",
                text=self._field_value(record.fields, "Notes"),
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
