"""Native Markdown/YAML codec for Manuskript Project Format 2."""

import posixpath
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import yaml

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
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
        normalized = {
            str(path).replace("\\", "/"): content
            for path, content in files.items()
        }
        issues: List[ProjectIssue] = []
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
        listed_paths = {item.source_path for item in self._walk(outline)}
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
            "format", "metadata", "summary", "labels", "statuses", "outline"
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
        original = {item.path: item.content for item in project.source_files}
        if original and self.decode(original, zipped=project.zipped) == project:
            return EncodedProject(
                2, tuple((path, original[path]) for path in sorted(original))
            )

        outline = self._assign_paths(project.outline)
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
        assigned = set()
        for index, document in enumerate(outline):
            self._encode_document(document, files, assigned, index)
        for item in project.plugin_files + project.unknown_files:
            files[item.path] = item.content
        return EncodedProject(
            2, tuple((path, files[path]) for path in sorted(files))
        )

    def validate(self, project: CanonicalProject) -> Tuple[ProjectIssue, ...]:
        issues = list(project.issues)
        ids = set()
        paths = set()
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
            normalized_path = posixpath.normpath(document.source_path).casefold()
            if normalized_path in paths:
                issues.append(ProjectIssue(
                    "error", "Duplicate document path.",
                    SourceLocation(document.source_path),
                ))
            paths.add(normalized_path)
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
            document = documents.get(path)
            if document is None:
                issues.append(ProjectIssue(
                    "error", "Outline entry refers to a missing document.",
                    SourceLocation(PROJECT_FILE, path),
                ))
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

    @staticmethod
    def _replace_children(document, children):
        from dataclasses import replace
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

    def _assign_paths(self, records):
        from dataclasses import replace

        used = set()

        def assign(document, index):
            path = document.source_path or self._new_document_path(
                document, index
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

    def _encode_document(self, document, files, assigned, index):
        path = document.source_path or self._new_document_path(document, index)
        if path in assigned:
            raise ValueError("Two Format 2 documents use {}.".format(path))
        assigned.add(path)
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
    def _new_document_path(document, index):
        slug = re.sub(r"[^\w.-]+", "-", document.title, flags=re.UNICODE).strip("-")
        slug = slug or "document"
        return "Manuscript/{:04d}-{}-{}.md".format(index, slug, document.id)

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
