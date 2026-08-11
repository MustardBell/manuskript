"""Qt-independent codec for the folder/archive Manuskript v1 format."""

import posixpath
import re
import string
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from lxml import etree as ET

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
    WorldRecord,
)
from manuskript.load_save.mmd import encode_mmd, format_metadata, parse_mmd
from manuskript.load_save.project_codec import EncodedProject
from manuskript.load_save.xml import parse_project_xml


REQUIRED_FILES = (
    "settings.txt",
    "labels.txt",
    "status.txt",
    "infos.txt",
    "summary.txt",
    "plots.xml",
    "world.opml",
)

CHARACTER_FIELDS = (
    "Name",
    "ID",
    "Importance",
    "POV",
    "Motivation",
    "Goal",
    "Conflict",
    "Epiphany",
    "Phrase Summary",
    "Paragraph Summary",
    "Full Summary",
    "Notes",
)


@dataclass
class _OutlineBuilder:
    document: Optional[OutlineDocument] = None
    children: Dict[str, "_OutlineBuilder"] = field(default_factory=dict)


class Version1ProjectCodec:
    format_version = 1

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
        metadata = self._mmd_fields(normalized, "infos.txt", issues)
        summary = self._mmd_fields(normalized, "summary.txt", issues)
        labels = self._labels(normalized, issues)
        statuses = self._statuses(normalized)
        characters = self._characters(normalized, issues)
        outline = self._outline(normalized, issues)
        world = self._world(normalized, issues)
        plots = self._plots(normalized, issues)
        revisions = self._revisions(normalized, issues)

        recognized = set(REQUIRED_FILES)
        recognized.add("MANUSKRIPT")
        recognized.add("revisions.xml")
        recognized.update(
            path for path in normalized
            if path.startswith("characters/")
            or path.startswith("outline/")
        )
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
        source_files = tuple(
            PreservedProjectFile(path, normalized[path], "source")
            for path in sorted(normalized)
        )

        for path in REQUIRED_FILES:
            if path not in normalized:
                issues.append(ProjectIssue(
                    "warning",
                    "Required v1 project file is missing.",
                    SourceLocation(path),
                ))

        return CanonicalProject(
            format_version=1,
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
            settings_source=normalized.get("settings.txt"),
            plugin_files=plugin_files,
            unknown_files=unknown_files,
            issues=tuple(issues),
            source_files=source_files,
        )

    def encode(self, project: CanonicalProject) -> EncodedProject:
        if project.format_version != self.format_version:
            raise ValueError("Version 1 codec can only encode version 1 projects.")

        original = {item.path: item.content for item in project.source_files}
        if original:
            decoded = self.decode(original, zipped=project.zipped)
            if decoded == project:
                return EncodedProject(
                    format_version=1,
                    files=tuple((path, original[path]) for path in sorted(original)),
                )

        files: Dict[str, ProjectContent] = {
            "MANUSKRIPT": "1",
            "infos.txt": encode_mmd(project.metadata, tab_length=15).rstrip("\n"),
            "summary.txt": encode_mmd(project.summary, tab_length=12).rstrip("\n"),
            "labels.txt": self._encode_labels(project.labels),
            "status.txt": "".join(status + "\n" for status in project.statuses),
            "settings.txt": project.settings_source or "",
            "world.opml": self._encode_world(project.world),
            "plots.xml": self._encode_plots(project.plots),
        }
        for character in project.characters:
            path = character.source_path or posixpath.join(
                "characters",
                "{}-{}.txt".format(
                    character.id,
                    self._slugify(character.name),
                ),
            )
            fields = list(character.fields)
            if character.color:
                fields.append(MetadataField("Color", character.color))
            fields.extend(character.custom_fields)
            files[path] = "".join(
                format_metadata(item, tab_length=20) for item in fields
            )
        for document in project.outline:
            self._encode_outline_document(document, files)
        if project.revisions:
            files["revisions.xml"] = self._encode_revisions(project.revisions)
        for preserved in project.plugin_files + project.unknown_files:
            files[preserved.path] = preserved.content
        return EncodedProject(
            format_version=1,
            files=tuple((path, files[path]) for path in sorted(files)),
        )

    def validate(self, project: CanonicalProject) -> Tuple[ProjectIssue, ...]:
        issues = list(project.issues)
        seen_ids = set()
        for document in project.documents():
            if not document.id:
                issues.append(ProjectIssue(
                    "error", "Outline document has no stable legacy ID.",
                    SourceLocation(document.source_path, "ID"),
                ))
            elif document.id in seen_ids:
                issues.append(ProjectIssue(
                    "error", "Duplicate outline document ID: {}".format(document.id),
                    SourceLocation(document.source_path, "ID"),
                ))
            seen_ids.add(document.id)
        return tuple(issues)

    @staticmethod
    def _text(
        files: Mapping[str, ProjectContent],
        path: str,
        issues: List[ProjectIssue],
    ) -> Optional[str]:
        content = files.get(path)
        if content is None:
            return None
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

    def _mmd_fields(
        self,
        files: Mapping[str, ProjectContent],
        path: str,
        issues: List[ProjectIssue],
    ) -> Tuple[MetadataField, ...]:
        text = self._text(files, path, issues)
        return parse_mmd(text).metadata if text is not None else ()

    def _labels(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[LabelRecord, ...]:
        text = self._text(files, "labels.txt", issues)
        if text is None:
            return ()
        labels = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line:
                continue
            match = re.match(r"^(.*?):\s*(.*)$", line)
            if match is None:
                labels.append(LabelRecord(line))
                issues.append(ProjectIssue(
                    "warning", "Label has no explicit colour.",
                    SourceLocation("labels.txt", line=number),
                ))
                continue
            labels.append(LabelRecord(match.group(1), match.group(2)))
        return tuple(labels)

    def _statuses(
        self,
        files: Mapping[str, ProjectContent],
    ) -> Tuple[str, ...]:
        content = files.get("status.txt", "")
        if isinstance(content, bytes):
            try:
                content = content.decode("utf-8")
            except UnicodeDecodeError:
                return ()
        return tuple(line for line in content.splitlines() if line)

    def _characters(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[CharacterRecord, ...]:
        records = []
        for path in sorted(files):
            if not path.startswith("characters/") or path.endswith("/"):
                continue
            text = self._text(files, path, issues)
            if text is None:
                continue
            parsed = parse_mmd(text)
            standard = []
            custom = []
            color = ""
            for item in parsed.metadata:
                if item.name in CHARACTER_FIELDS:
                    standard.append(item)
                elif item.name == "Color" and not color:
                    color = item.value
                else:
                    custom.append(item)
            values = {item.name: item.value for item in standard}
            record_id = values.get("ID", "")
            if not record_id:
                record_id = self._id_from_character_path(path)
                issues.append(ProjectIssue(
                    "warning", "Character ID recovered from its filename.",
                    SourceLocation(path, "ID"),
                ))
            records.append(CharacterRecord(
                id=record_id,
                name=values.get("Name", ""),
                fields=tuple(standard),
                custom_fields=tuple(custom),
                color=color,
                source_path=path,
                raw_source=text,
            ))
        return tuple(records)

    def _outline(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[OutlineDocument, ...]:
        root = _OutlineBuilder()
        paths = sorted(
            path for path in files
            if path.startswith("outline/") and not path.endswith("/")
        )
        for path in paths:
            text = self._text(files, path, issues)
            if text is None:
                continue
            relative = path[len("outline/"):]
            parts = relative.split("/")
            is_folder = parts[-1] == "folder.txt"
            logical_parts = parts[:-1] if is_folder else parts
            if not logical_parts:
                issues.append(ProjectIssue(
                    "warning", "Outline root metadata is not an outline item.",
                    SourceLocation(path),
                ))
                continue
            builder = root
            for part in logical_parts:
                builder = builder.children.setdefault(part, _OutlineBuilder())
            parsed = parse_mmd(text)
            values = {item.name: item.value for item in parsed.metadata}
            document_id = values.get("ID", "")
            if not document_id:
                document_id = "missing:{}".format(path)
                issues.append(ProjectIssue(
                    "error", "Outline document has no ID; a recovery ID was assigned.",
                    SourceLocation(path, "ID"),
                ))
            builder.document = OutlineDocument(
                id=document_id,
                title=values.get("title", values.get("Title", logical_parts[-1])),
                kind=values.get("type", "folder" if is_folder else "md"),
                text=parsed.body,
                metadata=parsed.metadata,
                source_path=path,
                source_format="mmd",
                raw_source=text,
            )
        return tuple(
            self._finish_outline(name, builder, "outline", issues)
            for name, builder in root.children.items()
        )

    def _finish_outline(
        self,
        name: str,
        builder: _OutlineBuilder,
        parent_path: str,
        issues: List[ProjectIssue],
    ) -> OutlineDocument:
        child_path = posixpath.join(parent_path, name)
        children = tuple(
            self._finish_outline(child_name, child, child_path, issues)
            for child_name, child in builder.children.items()
        )
        if builder.document is None:
            issues.append(ProjectIssue(
                "warning", "Outline directory has no folder.txt metadata.",
                SourceLocation(child_path),
            ))
            return OutlineDocument(
                id="missing:{}".format(child_path),
                title=name,
                kind="folder",
                text="",
                children=children,
                source_path=posixpath.join(child_path, "folder.txt"),
            )
        return replace(builder.document, children=children)

    def _world(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[WorldRecord, ...]:
        content = files.get("world.opml")
        if content is None:
            return ()
        try:
            root = parse_project_xml(content)
            body = root.find("body")
            if body is None:
                raise ValueError("OPML body is missing")
            return tuple(self._world_record(item) for item in body)
        except (ET.XMLSyntaxError, TypeError, ValueError) as error:
            issues.append(ProjectIssue(
                "error", "Cannot parse world.opml: {}".format(error),
                SourceLocation("world.opml"),
            ))
            return ()

    def _world_record(self, element: ET._Element) -> WorldRecord:
        return WorldRecord(
            fields=tuple(
                MetadataField(name, value)
                for name, value in element.attrib.items()
            ),
            children=tuple(self._world_record(child) for child in element),
        )

    def _plots(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[PlotRecord, ...]:
        content = files.get("plots.xml")
        if content is None:
            return ()
        try:
            root = parse_project_xml(content)
            records = []
            for element in root:
                attributes = tuple(
                    MetadataField(name, value)
                    for name, value in element.attrib.items()
                    if name != "characters"
                )
                characters = tuple(
                    value.strip()
                    for value in element.attrib.get("characters", "").split(",")
                    if value.strip()
                )
                steps = tuple(
                    PlotStepRecord(tuple(
                        MetadataField(name, value)
                        for name, value in child.attrib.items()
                    ))
                    for child in element
                )
                records.append(PlotRecord(attributes, characters, steps))
            return tuple(records)
        except (ET.XMLSyntaxError, TypeError, ValueError) as error:
            issues.append(ProjectIssue(
                "error", "Cannot parse plots.xml: {}".format(error),
                SourceLocation("plots.xml"),
            ))
            return ()

    def _revisions(
        self,
        files: Mapping[str, ProjectContent],
        issues: List[ProjectIssue],
    ) -> Tuple[RevisionRecord, ...]:
        content = files.get("revisions.xml")
        if content is None:
            return ()
        try:
            root = parse_project_xml(content)
        except (ET.XMLSyntaxError, TypeError, ValueError) as error:
            issues.append(ProjectIssue(
                "error", "Cannot parse revisions.xml: {}".format(error),
                SourceLocation("revisions.xml"),
            ))
            return ()
        revisions = []
        for owner in root.iter("outlineItem"):
            document_id = owner.attrib.get("ID", "")
            for revision in owner:
                if revision.tag != "revision":
                    continue
                revisions.append(RevisionRecord(
                    document_id=document_id,
                    timestamp=revision.attrib.get("timestamp", ""),
                    text=revision.attrib.get("text", revision.text or ""),
                ))
        return tuple(revisions)

    @staticmethod
    def _encode_labels(labels: Iterable[LabelRecord]) -> str:
        return "".join(
            "{}{}\n".format(
                item.name,
                ":" + " " * max(1, 20 - len(item.name)) + item.color
                if item.color else "",
            )
            for item in labels
        )

    def _encode_outline_document(
        self,
        document: OutlineDocument,
        files: Dict[str, ProjectContent],
    ) -> None:
        path = document.source_path
        if not path:
            filename = self._slugify(document.title)
            if document.kind == "folder":
                path = posixpath.join("outline", filename, "folder.txt")
            else:
                path = posixpath.join("outline", filename + ".md")
        files[path] = encode_mmd(document.metadata, document.text)
        for child in document.children:
            self._encode_outline_document(child, files)

    @staticmethod
    def _encode_world(records: Iterable[WorldRecord]) -> bytes:
        root = ET.Element("opml", version="1.0")
        body = ET.SubElement(root, "body")

        def append(parent: ET._Element, record: WorldRecord) -> None:
            element = ET.SubElement(parent, "outline")
            for item in record.fields:
                element.attrib[item.name] = item.value
            for child in record.children:
                append(element, child)

        for record in records:
            append(body, record)
        return ET.tostring(
            root, encoding="UTF-8", xml_declaration=True, pretty_print=True
        )

    @staticmethod
    def _encode_plots(records: Iterable[PlotRecord]) -> bytes:
        root = ET.Element("root")
        for record in records:
            element = ET.SubElement(root, "plot")
            for item in record.fields:
                element.attrib[item.name] = item.value
            if record.character_ids:
                element.attrib["characters"] = ",".join(record.character_ids)
            for step in record.steps:
                child = ET.SubElement(element, "step")
                for item in step.fields:
                    child.attrib[item.name] = item.value
        return ET.tostring(
            root, encoding="UTF-8", xml_declaration=True, pretty_print=True
        )

    @staticmethod
    def _encode_revisions(revisions: Iterable[RevisionRecord]) -> bytes:
        root = ET.Element("revisions")
        owners: Dict[str, ET._Element] = {}
        for revision in revisions:
            owner = owners.get(revision.document_id)
            if owner is None:
                owner = ET.SubElement(
                    root, "outlineItem", ID=revision.document_id
                )
                owners[revision.document_id] = owner
            ET.SubElement(
                owner,
                "revision",
                timestamp=revision.timestamp,
                text=revision.text,
            )
        return ET.tostring(
            root, encoding="UTF-8", xml_declaration=True, pretty_print=True
        )

    @staticmethod
    def _id_from_character_path(path: str) -> str:
        match = re.match(r"^([^-/]+)-", posixpath.basename(path))
        return match.group(1) if match else "missing:{}".format(path)

    @staticmethod
    def _slugify(name: str) -> str:
        valid = string.ascii_letters + string.digits
        return "".join(
            character if character in valid
            else "_" if character in string.whitespace
            else "-"
            for character in name
        )
