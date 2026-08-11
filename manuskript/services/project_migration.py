"""Validated copy-only project migration through canonical codecs."""

import os
import posixpath
import shutil
import tempfile
from dataclasses import dataclass, replace

from manuskript.domain.reference_index import ReferenceDocument, ReferenceIndex
from manuskript.load_save.format_detection import ProjectFormatDetector
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.version_1_codec import Version1ProjectCodec
from manuskript.load_save.version_2_codec import Version2ProjectCodec


@dataclass(frozen=True)
class MigrationSection:
    name: str
    converted: int
    source: int


@dataclass(frozen=True)
class ProjectMigrationReport:
    source_file: str
    destination_file: str
    source_version: int
    destination_version: int
    sections: tuple[MigrationSection, ...]
    plugin_files_preserved: int
    plugin_files_source: int
    unknown_files_preserved: int
    unknown_files_source: int
    unknown_fields_preserved: int
    unknown_fields_source: int
    broken_references: int
    warnings: tuple[str, ...] = ()

    @property
    def succeeded(self):
        return (
            all(item.converted == item.source for item in self.sections)
            and self.plugin_files_preserved == self.plugin_files_source
            and self.unknown_files_preserved == self.unknown_files_source
            and self.unknown_fields_preserved == self.unknown_fields_source
            and not any(item.startswith("PRESERVATION:") for item in self.warnings)
        )

    def render_text(self):
        lines = [
            "Format {} → Format {}".format(
                self.source_version, self.destination_version
            ),
            "",
        ]
        lines.extend(
            "{}: {} / {} converted".format(
                item.name, item.converted, item.source
            )
            for item in self.sections
        )
        lines.extend((
            "Plugin files: {} / {} preserved".format(
                self.plugin_files_preserved, self.plugin_files_source
            ),
            "Unknown files: {} / {} preserved".format(
                self.unknown_files_preserved, self.unknown_files_source
            ),
            "Unknown fields: {} / {} preserved".format(
                self.unknown_fields_preserved, self.unknown_fields_source
            ),
            "Broken references: {}".format(self.broken_references),
            "Warnings: {}".format(len(self.warnings)),
        ))
        lines.extend("- {}".format(item) for item in self.warnings)
        return "\n".join(lines)


class ProjectMigrationService:
    """Upgrade into a new path; never mutate or replace the source."""

    def __init__(
        self,
        detector=None,
        files=None,
        version_1_codec=None,
        version_2_codec=None,
    ):
        self.detector = detector or ProjectFormatDetector()
        self.files = files or Version1ProjectFiles()
        self.version_1_codec = version_1_codec or Version1ProjectCodec()
        self.version_2_codec = version_2_codec or Version2ProjectCodec()

    def upgrade_copy(self, source_file, destination_file):
        source_file = os.path.abspath(str(source_file))
        destination_file = os.path.abspath(str(destination_file))
        if source_file == destination_file:
            raise ValueError("Migration destination must be a separate copy.")
        destination_root = _project_root(destination_file)
        if os.path.exists(destination_file) or os.path.exists(destination_root):
            raise FileExistsError(
                "Migration destination already exists: {}".format(
                    destination_file
                )
            )
        detected = self.detector.detect(source_file)
        if detected.version != 1:
            raise ValueError(
                "Only Project Format 1 can be upgraded; found {}.".format(
                    detected.version
                )
            )
        read = self.files.read(source_file, zipped=detected.zipped)
        if read.unreadable_files:
            raise ValueError(
                "Migration source has unreadable files: {}".format(
                    ", ".join(read.unreadable_files)
                )
            )
        source = self.version_1_codec.decode(
            read.files, zipped=detected.zipped
        )
        migrated = _native_format_2_project(source)
        validation = tuple(
            item for item in self.version_2_codec.validate(migrated)
            if item.severity == "error"
        )
        if validation:
            raise ValueError("Migration validation failed: {}".format(
                "; ".join(item.message for item in validation)
            ))
        encoded = self.version_2_codec.encode(migrated)
        reopened = self.version_2_codec.decode(
            dict(encoded.files), zipped=detected.zipped
        )
        reopened_errors = tuple(
            item for item in self.version_2_codec.validate(reopened)
            if item.severity == "error"
        )
        if reopened_errors:
            raise ValueError("Migrated copy failed reopen validation: {}".format(
                "; ".join(item.message for item in reopened_errors)
            ))
        report = _report(source_file, destination_file, source, reopened)
        if not report.succeeded:
            raise ValueError(
                "Migration preservation validation failed: {}".format(
                    "; ".join(report.warnings) or "converted counts differ"
                )
            )
        self._write_validated_copy(
            destination_file,
            encoded.files,
            zipped=detected.zipped,
        )
        return report

    def _write_validated_copy(self, destination_file, encoded_files, *, zipped):
        parent = os.path.dirname(destination_file) or os.curdir
        os.makedirs(parent, exist_ok=True)
        temporary = tempfile.mkdtemp(prefix=".manuskript-upgrade-", dir=parent)
        temporary_file = os.path.join(
            temporary, os.path.basename(destination_file)
        )
        try:
            result = self.files.write(
                temporary_file,
                zipped=zipped,
                files=encoded_files,
                moves=(),
                cache={},
                marker_version=2,
            )
            if not result.succeeded:
                raise OSError("Cannot write migrated copy: {}".format(
                    ", ".join(result.failed_files)
                ))
            if zipped:
                os.replace(temporary_file, destination_file)
                return
            temporary_root = _project_root(temporary_file)
            destination_root = _project_root(destination_file)
            os.replace(temporary_root, destination_root)
            try:
                os.replace(temporary_file, destination_file)
            except Exception:
                os.replace(destination_root, temporary_root)
                raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


def _native_format_2_project(project):
    # Format 1 stores folder records in ``folder.txt`` while Format 2 only
    # discovers native Markdown documents.  Reserve existing Markdown paths
    # first so converting a legacy address can never displace one of them.
    markdown_paths = {
        item.source_path.casefold()
        for item in project.documents()
        if item.source_path.casefold().endswith(".md")
    }

    def markdown_path(path):
        if not path or path.casefold().endswith(".md"):
            return path
        stem, _extension = posixpath.splitext(path)
        candidate = stem + ".md"
        key = candidate.casefold()
        if key in markdown_paths:
            # Leaving the address empty delegates collision-safe path
            # generation to the Format 2 codec.
            return ""
        markdown_paths.add(key)
        return candidate

    def document(item):
        return replace(
            item,
            children=tuple(document(child) for child in item.children),
            source_path=markdown_path(item.source_path),
            source_format="markdown",
            raw_source=None,
        )

    return replace(
        project,
        format_version=2,
        outline=tuple(document(item) for item in project.outline),
        entities=tuple(
            replace(entity, document=document(entity.document))
            for entity in project.entities
        ),
        source_files=(),
        issues=(),
    )


def _report(source_file, destination_file, source, reopened):
    source_documents = tuple(source.documents())
    destination_documents = tuple(reopened.documents())
    references = ReferenceIndex()
    references.rebuild(tuple(
        ReferenceDocument(
            item.id, item.source_path, item.title, item.text
        )
        for item in destination_documents
    ))
    source_plot_steps = sum(len(item.steps) for item in source.plots)
    destination_plot_steps = sum(len(item.steps) for item in reopened.plots)
    sections = (
        MigrationSection("Outline", len(destination_documents), len(source_documents)),
        MigrationSection("Characters", len(reopened.characters), len(source.characters)),
        MigrationSection("World", _world_count(reopened.world), _world_count(source.world)),
        MigrationSection("Plots", len(reopened.plots), len(source.plots)),
        MigrationSection("Plot steps", destination_plot_steps, source_plot_steps),
        MigrationSection("Revisions", len(reopened.revisions), len(source.revisions)),
    )
    warnings = tuple(
        "{}: {}".format(item.source.path, item.message)
        for item in reopened.issues if item.severity != "error"
    ) + _preservation_warnings(source, reopened)
    source_unknown_fields = _unknown_field_count(source)
    reopened_unknown_fields = _unknown_field_count(reopened)
    return ProjectMigrationReport(
        source_file,
        destination_file,
        1,
        2,
        sections,
        len(reopened.plugin_files),
        len(source.plugin_files),
        len(reopened.unknown_files),
        len(source.unknown_files),
        reopened_unknown_fields,
        source_unknown_fields,
        len(references.broken()),
        warnings,
    )


def _world_count(items):
    return sum(1 + _world_count(item.children) for item in items)


def _unknown_field_count(project):
    return len(project.structured_metadata) + sum(
        len(item.structured_metadata) for item in project.documents()
    )


def _preservation_warnings(source, reopened):
    warnings = []
    for label, before, after in (
        ("plugin file", source.plugin_files, reopened.plugin_files),
        ("unknown file", source.unknown_files, reopened.unknown_files),
    ):
        before_by_path = {item.path: item.content for item in before}
        after_by_path = {item.path: item.content for item in after}
        for path in sorted(before_by_path.keys() - after_by_path.keys()):
            warnings.append(
                "PRESERVATION: {} {!r} was not preserved.".format(label, path)
            )
        for path in sorted(before_by_path.keys() & after_by_path.keys()):
            if before_by_path[path] != after_by_path[path]:
                warnings.append(
                    "PRESERVATION: {} {!r} changed content.".format(label, path)
                )
    if _structured_metadata(source) != _structured_metadata(reopened):
        warnings.append(
            "PRESERVATION: unknown structured metadata changed during conversion."
        )
    return tuple(warnings)


def _structured_metadata(project):
    return (
        project.structured_metadata,
        tuple(
            (item.id, item.structured_metadata)
            for item in project.documents()
        ),
        tuple(
            (item.id, item.metadata)
            for item in project.entities
        ),
    )


def _project_root(project_file):
    directory = os.path.dirname(project_file)
    folder = os.path.splitext(os.path.basename(project_file))[0]
    return os.path.join(directory, folder)
