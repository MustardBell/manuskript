"""Native Markdown/YAML codec for Manuskript Project Format 2."""

import posixpath
import re
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    EntityRecord,
    LabelRecord,
    MetadataField,
    OutlineDocument,
    PlotRecord,
    PlotStepRecord,
    PreservedProjectFile,
    ProjectContent,
    ProjectIssue,
    RevisionRecord,
    SourceLocation,
    StructuredMetadataField,
    WorldRecord,
)
from manuskript.domain.project_paths import normalize_project_path
from manuskript.load_save.frontmatter import (
    encode_frontmatter,
    parse_frontmatter,
)
from manuskript.load_save.mmd import parse_mmd
from manuskript.load_save.project_codec import EncodedProject


PROJECT_FILE = "project.yaml"
SETTINGS_FILE = ".manuskript/settings.json"
LEGACY_FILE = ".manuskript/legacy.yaml"


class Version2ProjectCodec:
    format_version = 2

    def decode(
        self,
        files: Mapping[str, ProjectContent],
        *,
        zipped: bool = False,
    ) -> CanonicalProject:
        issues: List[ProjectIssue] = []
        normalized = {}
        for raw_path, content in files.items():
            try:
                path = normalize_project_path(raw_path)
            except ValueError as error:
                issues.append(ProjectIssue(
                    "error", str(error), SourceLocation(str(raw_path))
                ))
                continue
            if path in normalized:
                issues.append(ProjectIssue(
                    "error",
                    "Multiple project files normalize to the same path.",
                    SourceLocation(path),
                ))
                continue
            normalized[path] = content
        project_data = self._load_yaml(normalized, PROJECT_FILE, issues)
        root = project_data.get("manuskript", {})
        if not isinstance(root, dict):
            issues.append(ProjectIssue(
                "error", "project.yaml manuskript value must be a mapping.",
                SourceLocation(PROJECT_FILE, "manuskript"),
            ))
            root = {}
        if root.get("format") != 2:
            issues.append(ProjectIssue(
                "error", "project.yaml does not declare format 2.",
                SourceLocation(PROJECT_FILE, "manuskript.format"),
            ))

        metadata = self._metadata(root.get("metadata"), PROJECT_FILE, issues)
        summary = self._metadata(root.get("summary"), PROJECT_FILE, issues)
        labels = tuple(
            LabelRecord(
                str(item.get("name", "")),
                str(item.get("color", "")),
            )
            for item in root.get("labels", ())
            if isinstance(item, dict) and item.get("name")
        )
        statuses = tuple(str(value) for value in root.get("statuses", ()))

        documents_by_path = self._documents(normalized, issues)
        outline = self._outline(
            root.get("outline", ()), documents_by_path, issues
        )
        entities = self._entities(
            root.get("entities", []), documents_by_path, issues
        )
        listed_paths = {item.source_path for item in self._walk(outline)}
        listed_paths.update(
            entity.document.source_path for entity in entities
        )
        unlisted = [
            document for path, document in documents_by_path.items()
            if path not in listed_paths
        ]
        for document in unlisted:
            issues.append(ProjectIssue(
                "warning",
                "Markdown document is not listed in the project outline; "
                "it was recovered at the root.",
                SourceLocation(document.source_path),
            ))
        outline = outline + tuple(unlisted)

        legacy = self._load_yaml(normalized, LEGACY_FILE, issues)
        characters = self._decode_characters(legacy.get("characters", ()))
        world = tuple(
            self._decode_world(item)
            for item in legacy.get("world", ())
            if isinstance(item, dict)
        )
        plots = tuple(
            self._decode_plot(item)
            for item in legacy.get("plots", ())
            if isinstance(item, dict)
        )
        revisions = tuple(
            RevisionRecord(
                str(item.get("document_id", "")),
                str(item.get("timestamp", "")),
                str(item.get("text", "")),
            )
            for item in legacy.get("revisions", ())
            if isinstance(item, dict)
        )

        known_root = {
            "format", "metadata", "summary", "labels", "statuses",
            "outline", "entities",
        }
        structured = [
            StructuredMetadataField(name, value)
            for name, value in project_data.items()
            if name != "manuskript"
        ]
        structured.extend(
            StructuredMetadataField("manuskript." + name, value)
            for name, value in root.items()
            if name not in known_root
        )

        recognized = {
            "MANUSKRIPT", PROJECT_FILE, SETTINGS_FILE, LEGACY_FILE,
        }
        recognized.update(documents_by_path)
        plugin_files = tuple(
            PreservedProjectFile(path, normalized[path], "plugin-owned")
            for path in sorted(normalized)
            if path.startswith("plugins/")
        )
        recognized.update(item.path for item in plugin_files)
        unknown_files = tuple(
            PreservedProjectFile(path, normalized[path], "unknown")
            for path in sorted(normalized)
            if path not in recognized
        )
        return CanonicalProject(
            format_version=2,
            zipped=zipped,
            metadata=metadata,
            summary=summary,
            labels=labels,
            statuses=statuses,
            entities=entities,
            characters=characters,
            outline=outline,
            world=world,
            plots=plots,
            revisions=revisions,
            settings_source=normalized.get(SETTINGS_FILE),
            plugin_files=plugin_files,
            unknown_files=unknown_files,
            issues=tuple(issues),
            structured_metadata=tuple(structured),
            source_files=tuple(
                PreservedProjectFile(path, normalized[path], "source")
                for path in sorted(normalized)
            ),
        )

    def encode(self, project: CanonicalProject) -> EncodedProject:
        if project.format_version != 2:
            raise ValueError("Version 2 codec can only encode version 2 projects.")
        self._validate_output_addresses(project)
        original = {item.path: item.content for item in project.source_files}
        if original and self.decode(original, zipped=project.zipped) == project:
            return EncodedProject(
                2, tuple((path, original[path]) for path in sorted(original))
            )

        outline = self._assign_paths(project.outline)
        entities = self._assign_entity_paths(
            project.entities,
            {document.source_path.casefold() for document in self._walk(outline)},
        )
        top_level = {
            item.name: item.value
            for item in project.structured_metadata
            if not item.name.startswith("manuskript.")
        }
        root = {
            "format": 2,
            "metadata": self._encode_metadata(project.metadata),
            "summary": self._encode_metadata(project.summary),
            "labels": [
                {"name": item.name, "color": item.color}
                for item in project.labels
            ],
            "statuses": list(project.statuses),
            "outline": [self._outline_entry(item) for item in outline],
            "entities": [self._entity_entry(item) for item in entities],
        }
        root.update({
            item.name[len("manuskript."):]: item.value
            for item in project.structured_metadata
            if item.name.startswith("manuskript.")
        })
        top_level["manuskript"] = root
        files: Dict[str, ProjectContent] = {
            "MANUSKRIPT": "2",
            PROJECT_FILE: self._dump_yaml(top_level),
            SETTINGS_FILE: project.settings_source or "{}",
            LEGACY_FILE: self._encode_legacy(project),
        }
        assigned = {path.casefold() for path in files}
        for index, document in enumerate(outline):
            self._encode_document(document, files, assigned, index)
        for index, entity in enumerate(entities):
            self._encode_entity(entity, files, assigned, index)
        for item in project.plugin_files + project.unknown_files:
            path = normalize_project_path(item.path)
            key = path.casefold()
            if key in assigned:
                raise ValueError(
                    "Preserved project file collides with {}.".format(path)
                )
            assigned.add(key)
            files[path] = item.content
        return EncodedProject(
            2, tuple((path, files[path]) for path in sorted(files))
        )

    def validate(self, project: CanonicalProject) -> Tuple[ProjectIssue, ...]:
        issues = list(project.issues)
        ids = set()
        paths = {
            path.casefold()
            for path in ("MANUSKRIPT", PROJECT_FILE, SETTINGS_FILE, LEGACY_FILE)
        }
        for document in project.documents():
            if not document.id:
                issues.append(ProjectIssue(
                    "error", "Format 2 document has no stable ID.",
                    SourceLocation(document.source_path, "manuskript.id"),
                ))
            elif document.id in ids:
                issues.append(ProjectIssue(
                    "error", "Duplicate document ID: {}".format(document.id),
                    SourceLocation(document.source_path, "manuskript.id"),
                ))
            ids.add(document.id)
            if not document.source_path:
                continue
            try:
                normalized_path = normalize_project_path(
                    document.source_path
                ).casefold()
            except ValueError as error:
                issues.append(ProjectIssue(
                    "error", str(error), SourceLocation(document.source_path)
                ))
                continue
            if normalized_path in paths:
                issues.append(ProjectIssue(
                    "error", "Duplicate document path.",
                    SourceLocation(document.source_path),
                ))
            paths.add(normalized_path)
        for item in project.plugin_files + project.unknown_files:
            try:
                normalized_path = normalize_project_path(item.path).casefold()
            except ValueError as error:
                issues.append(ProjectIssue(
                    "error", str(error), SourceLocation(item.path)
                ))
                continue
            if normalized_path in paths:
                issues.append(ProjectIssue(
                    "error", "Duplicate project path.",
                    SourceLocation(item.path),
                ))
            paths.add(normalized_path)
        for entity in project.entities:
            if entity.document.kind != "entity":
                issues.append(ProjectIssue(
                    "error", "Entity document type must be 'entity'.",
                    SourceLocation(
                        entity.document.source_path, "manuskript.type"
                    ),
                ))
        return tuple(issues)

    def _documents(self, files, issues):
        documents = {}
        for path in sorted(files):
            if not path.casefold().endswith(".md"):
                continue
            text = self._text(files[path], path, issues)
            if text is None:
                continue
            try:
                parsed = parse_frontmatter(text)
            except ValueError as error:
                issues.append(ProjectIssue(
                    "error", str(error), SourceLocation(path)
                ))
                continue
            if not parsed.has_frontmatter:
                mmd = parse_mmd(text)
                values = {item.name: item.value for item in mmd.metadata}
                if any(
                    name in values for name in ("ID", "title", "type")
                ):
                    document_id = values.get("ID", "missing:{}".format(path))
                    if "ID" not in values:
                        issues.append(ProjectIssue(
                            "error",
                            "Legacy-MMD document has no stable ID; a recovery ID was assigned.",
                            SourceLocation(path, "ID"),
                        ))
                    documents[path] = OutlineDocument(
                        id=str(document_id),
                        title=str(values.get("title", posixpath.basename(path)[:-3])),
                        kind=str(values.get("type", "document")),
                        text=mmd.body,
                        metadata=mmd.metadata,
                        source_path=path,
                        source_format="mmd",
                        raw_source=text,
                    )
                    continue
                # Ordinary Obsidian/Markdown files without Manuskript
                # identity metadata belong to the vault, not the outline.
                continue
            if "manuskript" not in parsed.metadata:
                continue
            root = parsed.metadata.get("manuskript", {})
            if not isinstance(root, dict):
                root = {}
                issues.append(ProjectIssue(
                    "error", "Document manuskript frontmatter must be a mapping.",
                    SourceLocation(path, "manuskript"),
                ))
            document_id = str(root.get("id", ""))
            if not document_id:
                document_id = "missing:{}".format(path)
                issues.append(ProjectIssue(
                    "error", "Document has no stable ID; a recovery ID was assigned.",
                    SourceLocation(path, "manuskript.id"),
                ))
            known = {"id", "type", "title", "metadata"}
            structured = [
                StructuredMetadataField(name, value)
                for name, value in parsed.metadata.items()
                if name != "manuskript"
            ]
            structured.extend(
                StructuredMetadataField("manuskript." + name, value)
                for name, value in root.items()
                if name not in known
            )
            documents[path] = OutlineDocument(
                id=document_id,
                title=str(root.get("title", posixpath.basename(path)[:-3])),
                kind=str(root.get("type", "document")),
                text=parsed.body,
                metadata=self._metadata(root.get("metadata"), path, issues),
                source_path=path,
                source_format="yaml-frontmatter",
                raw_source=text,
                structured_metadata=tuple(structured),
            )
        return documents

    def _outline(self, entries, documents, issues):
        if not isinstance(entries, list):
            issues.append(ProjectIssue(
                "error", "Project outline must be a list.",
                SourceLocation(PROJECT_FILE, "manuskript.outline"),
            ))
            return ()

        def load(entry):
            if not isinstance(entry, dict):
                return None
            path = str(entry.get("path", "")).replace("\\", "/")
            document = self._manifest_document(
                entry, documents, issues, "Outline"
            )
            if document is None:
                return None
            declared_id = str(entry.get("id", document.id))
            if declared_id != document.id:
                issues.append(ProjectIssue(
                    "error", "Outline and document IDs disagree.",
                    SourceLocation(path, "manuskript.id"),
                ))
            children = tuple(
                child for child in (
                    load(value) for value in entry.get("children", ())
                ) if child is not None
            )
            return self._replace_children(document, children)

        return tuple(
            item for item in (load(entry) for entry in entries)
            if item is not None
        )

    def _entities(self, entries, documents, issues):
        if not isinstance(entries, list):
            issues.append(ProjectIssue(
                "error", "Project entities must be a list.",
                SourceLocation(PROJECT_FILE, "manuskript.entities"),
            ))
            return ()
        entities = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            document = self._manifest_document(
                entry, documents, issues, "Entity"
            )
            if document is None:
                continue
            declared_id = str(entry.get("id", document.id))
            if declared_id != document.id:
                issues.append(ProjectIssue(
                    "error", "Entity manifest and document IDs disagree.",
                    SourceLocation(
                        document.source_path, "manuskript.id"
                    ),
                ))
            structured = {
                item.name: item.value
                for item in document.structured_metadata
            }
            aliases_value = structured.get("aliases", ())
            if isinstance(aliases_value, str):
                aliases = (aliases_value,)
            elif isinstance(aliases_value, list):
                aliases = tuple(str(value) for value in aliases_value)
            else:
                aliases = ()
                if aliases_value:
                    issues.append(ProjectIssue(
                        "warning", "Entity aliases must be text or a list.",
                        SourceLocation(document.source_path, "aliases"),
                    ))
            entity_value = structured.get("entity", {})
            if not isinstance(entity_value, dict):
                entity_value = {}
                issues.append(ProjectIssue(
                    "error", "Entity metadata must be a mapping.",
                    SourceLocation(document.source_path, "entity"),
                ))
            entity_type = str(entity_value.get("type", "entity"))
            entity_metadata = self._structured_fields(
                entity_value.get("metadata"),
                document.source_path,
                "entity.metadata",
                issues,
            )
            document = replace(
                document,
                structured_metadata=tuple(
                    item for item in document.structured_metadata
                    if item.name not in ("aliases", "entity")
                ),
            )
            entities.append(EntityRecord(
                document=document,
                entity_type=entity_type,
                aliases=tuple(dict.fromkeys(
                    alias for alias in aliases if alias.strip()
                )),
                metadata=entity_metadata,
            ))
        return tuple(entities)

    @staticmethod
    def _manifest_document(entry, documents, issues, label):
        path = str(entry.get("path", "")).replace("\\", "/")
        document = documents.get(path)
        if document is not None:
            return document
        declared_id = str(entry.get("id", ""))
        candidates = tuple(
            value for value in documents.values()
            if declared_id and value.id == declared_id
        )
        if len(candidates) == 1:
            issues.append(ProjectIssue(
                "warning",
                "{} document moved from {} to {}; stable ID recovered it.".format(
                    label, path, candidates[0].source_path
                ),
                SourceLocation(PROJECT_FILE, path),
            ))
            return candidates[0]
        issues.append(ProjectIssue(
            "error", "{} entry refers to a missing document.".format(label),
            SourceLocation(PROJECT_FILE, path),
        ))
        return None

    @staticmethod
    def _structured_fields(value, path, field, issues):
        if value is None:
            return ()
        if isinstance(value, dict):
            return tuple(
                StructuredMetadataField(str(name), item)
                for name, item in value.items()
            )
        if isinstance(value, list):
            result = []
            for item in value:
                if not isinstance(item, dict) or "name" not in item:
                    issues.append(ProjectIssue(
                        "warning", "Invalid structured metadata entry.",
                        SourceLocation(path, field),
                    ))
                    continue
                result.append(StructuredMetadataField(
                    str(item["name"]), item.get("value")
                ))
            return tuple(result)
        issues.append(ProjectIssue(
            "error", "Structured metadata must be a mapping or list.",
            SourceLocation(path, field),
        ))
        return ()

    @staticmethod
    def _replace_children(document, children):
        return replace(document, children=children)

    @staticmethod
    def _walk(records):
        for record in records:
            yield record
            yield from Version2ProjectCodec._walk(record.children)

    @staticmethod
    def _metadata(value, path, issues):
        if value is None:
            return ()
        if isinstance(value, dict):
            return tuple(
                MetadataField(str(name), str(field_value))
                for name, field_value in value.items()
            )
        if isinstance(value, list):
            fields = []
            for item in value:
                if not isinstance(item, dict) or "name" not in item:
                    issues.append(ProjectIssue(
                        "warning", "Invalid metadata entry was preserved only in source.",
                        SourceLocation(path, "metadata"),
                    ))
                    continue
                fields.append(MetadataField(
                    str(item["name"]), str(item.get("value", ""))
                ))
            return tuple(fields)
        issues.append(ProjectIssue(
            "error", "Metadata must be a mapping or ordered list.",
            SourceLocation(path, "metadata"),
        ))
        return ()

    @staticmethod
    def _encode_metadata(fields):
        return [
            {"name": item.name, "value": item.value} for item in fields
        ]

    @staticmethod
    def _outline_entry(document):
        return {
            "id": document.id,
            "path": document.source_path,
            "children": [
                Version2ProjectCodec._outline_entry(child)
                for child in document.children
            ],
        }

    @staticmethod
    def _entity_entry(entity):
        return {
            "id": entity.id,
            "path": entity.document.source_path,
        }

    def _assign_paths(self, records):
        used = set()

        def assign(document, index):
            path = (
                normalize_project_path(document.source_path)
                if document.source_path
                else self._new_document_path(document, index)
            )
            candidate = path
            duplicate = 2
            while candidate.casefold() in used:
                stem, extension = posixpath.splitext(path)
                candidate = "{}-{}{}".format(stem, duplicate, extension)
                duplicate += 1
            used.add(candidate.casefold())
            return replace(
                document,
                source_path=candidate,
                children=tuple(
                    assign(child, child_index)
                    for child_index, child in enumerate(document.children)
                ),
            )

        return tuple(
            assign(document, index)
            for index, document in enumerate(records)
        )

    def _assign_entity_paths(self, entities, used_paths):
        used = set(used_paths)
        assigned = []
        for index, entity in enumerate(entities):
            document = entity.document
            path = (
                normalize_project_path(document.source_path)
                if document.source_path
                else self._new_entity_path(entity, index)
            )
            candidate = path
            duplicate = 2
            while candidate.casefold() in used:
                stem, extension = posixpath.splitext(path)
                candidate = "{}-{}{}".format(stem, duplicate, extension)
                duplicate += 1
            used.add(candidate.casefold())
            assigned.append(replace(
                entity,
                document=replace(document, source_path=candidate),
            ))
        return tuple(assigned)

    def _encode_document(self, document, files, assigned, index):
        path = document.source_path or self._new_document_path(document, index)
        key = path.casefold()
        if key in assigned:
            raise ValueError("Two Format 2 documents use {}.".format(path))
        assigned.add(key)
        if document.raw_source is not None and self._document_source_is_current(
            document
        ):
            files[path] = document.raw_source
            for child_index, child in enumerate(document.children):
                self._encode_document(child, files, assigned, child_index)
            return
        root = {
            "id": document.id,
            "type": document.kind,
            "title": document.title,
            "metadata": self._encode_metadata(tuple(
                item for item in document.metadata
                if document.source_format != "mmd"
                or item.name not in ("ID", "title", "type")
            )),
        }
        top_level = {
            item.name: item.value
            for item in document.structured_metadata
            if not item.name.startswith("manuskript.")
        }
        root.update({
            item.name[len("manuskript."):]: item.value
            for item in document.structured_metadata
            if item.name.startswith("manuskript.")
        })
        top_level["manuskript"] = root
        files[path] = encode_frontmatter(top_level, document.text)
        for child_index, child in enumerate(document.children):
            self._encode_document(child, files, assigned, child_index)

    def _encode_entity(self, entity, files, assigned, index):
        document = entity.document
        path = document.source_path or self._new_entity_path(entity, index)
        key = path.casefold()
        if key in assigned:
            raise ValueError("Two Format 2 documents use {}.".format(path))
        assigned.add(key)
        if document.raw_source is not None and self._entity_source_is_current(
            entity
        ):
            files[path] = document.raw_source
            return
        root = {
            "id": document.id,
            "type": "entity",
            "title": document.title,
            "metadata": self._encode_metadata(document.metadata),
        }
        root.update({
            item.name[len("manuskript."):]: item.value
            for item in document.structured_metadata
            if item.name.startswith("manuskript.")
        })
        top_level = {
            item.name: item.value
            for item in document.structured_metadata
            if not item.name.startswith("manuskript.")
        }
        top_level["aliases"] = list(entity.aliases)
        top_level["entity"] = {
            "type": entity.type,
            "metadata": [
                {"name": item.name, "value": item.value}
                for item in entity.metadata
            ],
        }
        top_level["manuskript"] = root
        files[path] = encode_frontmatter(top_level, document.text)

    @staticmethod
    def _document_source_is_current(document):
        if document.source_format == "mmd":
            parsed = parse_mmd(document.raw_source)
            values = {item.name: item.value for item in parsed.metadata}
            return (
                str(values.get("ID", "")) == document.id
                and str(values.get("title", "")) == document.title
                and str(values.get("type", "document")) == document.kind
                and parsed.body == document.text
                and parsed.metadata == document.metadata
            )
        try:
            parsed = parse_frontmatter(document.raw_source)
        except ValueError:
            return False
        root = parsed.metadata.get("manuskript", {})
        if not isinstance(root, dict):
            return False
        known = {"id", "type", "title", "metadata"}
        structured = [
            StructuredMetadataField(name, value)
            for name, value in parsed.metadata.items()
            if name != "manuskript"
        ]
        structured.extend(
            StructuredMetadataField("manuskript." + name, value)
            for name, value in root.items()
            if name not in known
        )
        raw_fields = root.get("metadata", ())
        if isinstance(raw_fields, dict):
            metadata = tuple(
                MetadataField(str(name), str(value))
                for name, value in raw_fields.items()
            )
        elif isinstance(raw_fields, list):
            metadata = tuple(
                MetadataField(str(item["name"]), str(item.get("value", "")))
                for item in raw_fields
                if isinstance(item, dict) and "name" in item
            )
        else:
            return False
        return (
            str(root.get("id", "")) == document.id
            and str(root.get("title", "")) == document.title
            and str(root.get("type", "document")) == document.kind
            and parsed.body == document.text
            and metadata == document.metadata
            and tuple(structured) == document.structured_metadata
        )

    @staticmethod
    def _entity_source_is_current(entity):
        document = entity.document
        try:
            parsed = parse_frontmatter(document.raw_source)
        except ValueError:
            return False
        if not parsed.has_frontmatter:
            return False
        root = parsed.metadata.get("manuskript", {})
        entity_value = parsed.metadata.get("entity", {})
        if not isinstance(root, dict) or not isinstance(entity_value, dict):
            return False
        aliases_value = parsed.metadata.get("aliases", ())
        if isinstance(aliases_value, str):
            aliases = (aliases_value,)
        elif isinstance(aliases_value, list):
            aliases = tuple(str(value) for value in aliases_value)
        else:
            return False
        raw_entity_metadata = entity_value.get("metadata", ())
        if isinstance(raw_entity_metadata, dict):
            entity_metadata = tuple(
                StructuredMetadataField(str(name), value)
                for name, value in raw_entity_metadata.items()
            )
        elif isinstance(raw_entity_metadata, list):
            entity_metadata = tuple(
                StructuredMetadataField(
                    str(item["name"]), item.get("value")
                )
                for item in raw_entity_metadata
                if isinstance(item, dict) and "name" in item
            )
        else:
            return False
        known = {"id", "type", "title", "metadata"}
        structured = [
            StructuredMetadataField(name, value)
            for name, value in parsed.metadata.items()
            if name not in ("manuskript", "aliases", "entity")
        ]
        structured.extend(
            StructuredMetadataField("manuskript." + name, value)
            for name, value in root.items()
            if name not in known
        )
        raw_fields = root.get("metadata", ())
        if isinstance(raw_fields, dict):
            document_metadata = tuple(
                MetadataField(str(name), str(value))
                for name, value in raw_fields.items()
            )
        elif isinstance(raw_fields, list):
            document_metadata = tuple(
                MetadataField(str(item["name"]), str(item.get("value", "")))
                for item in raw_fields
                if isinstance(item, dict) and "name" in item
            )
        else:
            return False
        return (
            str(root.get("id", "")) == document.id
            and str(root.get("title", "")) == document.title
            and str(root.get("type", "")) == "entity"
            and parsed.body == document.text
            and document_metadata == document.metadata
            and tuple(structured) == document.structured_metadata
            and aliases == entity.aliases
            and str(entity_value.get("type", "entity")) == entity.type
            and entity_metadata == entity.metadata
        )

    @staticmethod
    def _new_document_path(document, index):
        slug = re.sub(r"[^\w.-]+", "-", document.title, flags=re.UNICODE).strip("-")
        slug = slug or "document"
        return "Manuscript/{:04d}-{}-{}.md".format(index, slug, document.id)

    @staticmethod
    def _new_entity_path(entity, index):
        slug = re.sub(
            r"[^\w.-]+", "-", entity.title, flags=re.UNICODE
        ).strip("-") or "entity"
        return "Entities/{:04d}-{}-{}.md".format(index, slug, entity.id)

    @staticmethod
    def _validate_output_addresses(project):
        """Reject unsafe or colliding persisted addresses before encoding."""

        paths = {
            path.casefold()
            for path in ("MANUSKRIPT", PROJECT_FILE, SETTINGS_FILE, LEGACY_FILE)
        }
        items = tuple(
            document.source_path
            for document in project.documents()
            if document.source_path
        ) + tuple(
            item.path for item in project.plugin_files + project.unknown_files
        )
        for raw_path in items:
            path = normalize_project_path(raw_path)
            key = path.casefold()
            if key in paths:
                raise ValueError(
                    "Project paths collide at {}.".format(path)
                )
            paths.add(key)

        source_paths = set()
        for item in project.source_files:
            path = normalize_project_path(item.path)
            key = path.casefold()
            if key in source_paths:
                raise ValueError(
                    "Source project paths collide at {}.".format(path)
                )
            source_paths.add(key)

    def _decode_characters(self, values):
        return tuple(
            CharacterRecord(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                fields=self._fields(item.get("fields", ())),
                custom_fields=self._fields(item.get("custom_fields", ())),
                color=str(item.get("color", "")),
                source_path=str(item.get("source_path", "")),
            )
            for item in values if isinstance(item, dict)
        )

    def _decode_world(self, item):
        return WorldRecord(
            self._fields(item.get("fields", ())),
            tuple(
                self._decode_world(child)
                for child in item.get("children", ())
                if isinstance(child, dict)
            ),
        )

    def _decode_plot(self, item):
        return PlotRecord(
            self._fields(item.get("fields", ())),
            tuple(str(value) for value in item.get("character_ids", ())),
            tuple(
                PlotStepRecord(self._fields(step.get("fields", ())))
                for step in item.get("steps", ())
                if isinstance(step, dict)
            ),
        )

    @staticmethod
    def _fields(values):
        return tuple(
            MetadataField(str(item.get("name", "")), str(item.get("value", "")))
            for item in values if isinstance(item, dict) and item.get("name")
        )

    def _encode_legacy(self, project):
        data = {
            "characters": [
                {
                    "id": item.id,
                    "name": item.name,
                    "fields": self._encode_metadata(item.fields),
                    "custom_fields": self._encode_metadata(item.custom_fields),
                    "color": item.color,
                    "source_path": item.source_path,
                }
                for item in project.characters
            ],
            "world": [self._encode_world(item) for item in project.world],
            "plots": [self._encode_plot(item) for item in project.plots],
            "revisions": [
                {
                    "document_id": item.document_id,
                    "timestamp": item.timestamp,
                    "text": item.text,
                }
                for item in project.revisions
            ],
        }
        return self._dump_yaml(data)

    def _encode_world(self, item):
        return {
            "fields": self._encode_metadata(item.fields),
            "children": [self._encode_world(child) for child in item.children],
        }

    def _encode_plot(self, item):
        return {
            "fields": self._encode_metadata(item.fields),
            "character_ids": list(item.character_ids),
            "steps": [
                {"fields": self._encode_metadata(step.fields)}
                for step in item.steps
            ],
        }

    def _load_yaml(self, files, path, issues):
        content = files.get(path)
        if content is None:
            if path == PROJECT_FILE:
                issues.append(ProjectIssue(
                    "error", "Required Format 2 manifest is missing.",
                    SourceLocation(path),
                ))
            return {}
        text = self._text(content, path, issues)
        if text is None:
            return {}
        try:
            value = yaml.safe_load(text) or {}
        except yaml.YAMLError as error:
            issues.append(ProjectIssue(
                "error", "Cannot parse YAML: {}".format(error),
                SourceLocation(path),
            ))
            return {}
        if not isinstance(value, dict):
            issues.append(ProjectIssue(
                "error", "YAML project file must contain a mapping.",
                SourceLocation(path),
            ))
            return {}
        return value

    @staticmethod
    def _dump_yaml(value: Mapping[str, Any]) -> str:
        return yaml.safe_dump(
            dict(value), allow_unicode=True,
            default_flow_style=False, sort_keys=False,
        )

    @staticmethod
    def _text(content, path, issues):
        if isinstance(content, str):
            return content
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(ProjectIssue(
                "error", "Text project file is not valid UTF-8.",
                SourceLocation(path),
            ))
            return None
