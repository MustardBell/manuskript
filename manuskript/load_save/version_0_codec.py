"""Qt-independent reader for the original zipped Manuskript format."""

from typing import Dict, List, Mapping, Tuple

from lxml import etree as ET

from manuskript.domain.canonical_project import (
    CanonicalProject,
    LegacyCell,
    LegacyModel,
    PreservedProjectFile,
    ProjectContent,
    ProjectIssue,
    SourceLocation,
)
from manuskript.load_save.project_codec import EncodedProject
from manuskript.load_save.xml import parse_project_xml


MODEL_FILES = (
    "flatModel.xml",
    "perso.xml",
    "world.xml",
    "labels.xml",
    "status.xml",
    "plots.xml",
)


class Version0ProjectCodec:
    """Preserve the v0 item-model graph without constructing Qt objects.

    The old archive is intentionally represented faithfully rather than being
    forced into modern story entities during decoding.  A later adapter or
    migration can give those cells meaning with a report.
    """

    format_version = 0

    def decode(
        self,
        files: Mapping[str, ProjectContent],
        *,
        zipped: bool = True,
    ) -> CanonicalProject:
        normalized = {
            str(path).replace("\\", "/"): content
            for path, content in files.items()
        }
        models = []
        issues: List[ProjectIssue] = []
        recognized = set()
        for path in MODEL_FILES:
            content = normalized.get(path)
            if content is None:
                issues.append(ProjectIssue(
                    "warning", "Legacy model file is missing.",
                    SourceLocation(path),
                ))
                continue
            recognized.add(path)
            try:
                models.append(self._decode_model(path, content))
            except (ET.XMLSyntaxError, TypeError, ValueError) as error:
                issues.append(ProjectIssue(
                    "error", "Cannot parse legacy model: {}".format(error),
                    SourceLocation(path),
                ))

        # outline.xml is a specialized tree rather than a standard item model.
        # It remains source-preserved until the migration adapter interprets it.
        preserved_paths = {"outline.xml", "settings.txt", "settings.pickle"}
        recognized.update(path for path in preserved_paths if path in normalized)
        unknown = tuple(
            PreservedProjectFile(
                path,
                normalized[path],
                "legacy-specialized" if path in preserved_paths else "unknown",
            )
            for path in sorted(normalized)
            if path not in {item.name for item in models}
        )
        return CanonicalProject(
            format_version=0,
            zipped=True,
            settings_source=normalized.get("settings.txt"),
            unknown_files=unknown,
            legacy_models=tuple(models),
            issues=tuple(issues),
            source_files=tuple(
                PreservedProjectFile(path, normalized[path], "source")
                for path in sorted(normalized)
            ),
        )

    def encode(self, project: CanonicalProject) -> EncodedProject:
        if project.format_version != 0:
            raise ValueError("Version 0 codec can only encode version 0 projects.")
        original = {item.path: item.content for item in project.source_files}
        if original and self.decode(original) == project:
            return EncodedProject(
                format_version=0,
                files=tuple((path, original[path]) for path in sorted(original)),
            )
        files: Dict[str, ProjectContent] = {
            model.name: self._encode_model(model)
            for model in project.legacy_models
        }
        for item in project.unknown_files:
            files[item.path] = item.content
        if project.settings_source is not None:
            files["settings.txt"] = project.settings_source
        return EncodedProject(
            format_version=0,
            files=tuple((path, files[path]) for path in sorted(files)),
        )

    def validate(self, project: CanonicalProject) -> Tuple[ProjectIssue, ...]:
        return project.issues

    def _decode_model(
        self, path: str, content: ProjectContent
    ) -> LegacyModel:
        root = parse_project_xml(content)
        header = root.find("header")
        data = root.find("data")
        if header is None or data is None:
            raise ValueError("model header or data section is missing")
        horizontal = header.find("horizontal")
        vertical = header.find("vertical")
        horizontal_items = () if horizontal is None else horizontal
        vertical_items = () if vertical is None else vertical
        return LegacyModel(
            name=path,
            horizontal_headers=tuple(
                item.attrib.get("text", "")
                for item in horizontal_items
            ),
            vertical_headers=tuple(
                item.attrib.get("text", "")
                for item in vertical_items
            ),
            rows=tuple(self._decode_row(row) for row in data),
            raw_source=(
                content if isinstance(content, bytes)
                else content.encode("utf-8")
            ),
        )

    def _decode_row(self, row: ET._Element) -> Tuple[LegacyCell, ...]:
        columns = []
        for column in row:
            children = tuple(
                self._decode_row(child)
                for child in column
                if child.tag == "row"
            )
            columns.append(LegacyCell(
                text=column.text or "",
                color=column.attrib.get("color", ""),
                children=children,
            ))
        return tuple(columns)

    def _encode_model(self, model: LegacyModel) -> bytes:
        root = ET.Element("model")
        header = ET.SubElement(root, "header")
        vertical = ET.SubElement(header, "vertical")
        for index, text in enumerate(model.vertical_headers):
            ET.SubElement(vertical, "label", row=str(index), text=text)
        horizontal = ET.SubElement(header, "horizontal")
        for index, text in enumerate(model.horizontal_headers):
            ET.SubElement(horizontal, "label", row=str(index), text=text)
        data = ET.SubElement(root, "data")
        self._append_rows(data, model.rows)
        return ET.tostring(
            root, encoding="UTF-8", xml_declaration=True, pretty_print=True
        )

    def _append_rows(
        self,
        parent: ET._Element,
        rows: Tuple[Tuple[LegacyCell, ...], ...],
    ) -> None:
        for row_number, row in enumerate(rows):
            row_element = ET.SubElement(parent, "row", row=str(row_number))
            for column_number, cell in enumerate(row):
                column = ET.SubElement(
                    row_element, "col", col=str(column_number)
                )
                if cell.text:
                    column.text = cell.text
                if cell.color:
                    column.attrib["color"] = cell.color
                self._append_rows(column, cell.children)
