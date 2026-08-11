"""Translate between the canonical project and current Qt application models."""

import posixpath
import string
from dataclasses import replace
from typing import Dict, Iterable, List, Optional, Tuple

from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QColor, QStandardItem

from manuskript.converters import HTML2PlainText
from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    LabelRecord,
    MetadataField,
    OutlineDocument,
    PlotRecord,
    PlotStepRecord,
    PreservedProjectFile,
    RevisionRecord,
    WorldRecord,
)
from manuskript.enums import Character, Outline, Plot, PlotStep, World
from manuskript.functions import iconColor, iconFromColorString
from manuskript.models import outlineItem
from manuskript.models.characterModel import CharacterInfo


PROJECT_METADATA = (
    "Title", "Subtitle", "Serie", "Volume", "Genre", "License",
    "Author", "Email",
)
PROJECT_SUMMARY = (
    "Situation", "Sentence", "Paragraph", "Page", "Full",
)
CHARACTER_FIELD_TO_ENUM = {
    "Name": Character.name,
    "ID": Character.ID,
    "Importance": Character.importance,
    "POV": Character.pov,
    "Motivation": Character.motivation,
    "Goal": Character.goal,
    "Conflict": Character.conflict,
    "Epiphany": Character.epiphany,
    "Phrase Summary": Character.summarySentence,
    "Paragraph Summary": Character.summaryPara,
    "Full Summary": Character.summaryFull,
    "Notes": Character.notes,
}


class LegacyApplicationModelAdapter:
    """The only v1 boundary permitted to know both canonical records and Qt."""

    def hydrate(self, project: CanonicalProject, context) -> None:
        if project.format_version not in (1, 2):
            raise ValueError("The current application adapter accepts v1/v2 projects.")
        self._hydrate_settings(project, context.settings)
        self._hydrate_flat(project, context.models.flat_data)
        self._hydrate_labels(project, context.models.labels)
        self._hydrate_statuses(project, context.models.statuses)
        self._hydrate_characters(project, context.models.characters)
        self._hydrate_plots(project, context.models.plots)
        self._hydrate_world(project, context.models.world)
        self._hydrate_outline(project, context.models.outline)
        context.models.plugin_data.load_project_files({
            item.path: item.content for item in project.plugin_files
        })

    def capture(
        self,
        context,
        baseline: Optional[CanonicalProject] = None,
    ) -> CanonicalProject:
        baseline = baseline or CanonicalProject(format_version=1)
        metadata = self._capture_flat_row(
            context.models.flat_data, 0, PROJECT_METADATA, baseline.metadata
        )
        summary = self._capture_flat_row(
            context.models.flat_data, 1, PROJECT_SUMMARY, baseline.summary
        )
        characters = self._capture_characters(context.models.characters)
        outline = self._merge_outline_extensions(
            self._capture_outline(context.models.outline), baseline.outline,
            preserve_paths=baseline.format_version == 2,
        )
        return CanonicalProject(
            format_version=baseline.format_version,
            zipped=bool(context.settings.saveToZip),
            metadata=metadata,
            summary=summary,
            labels=self._capture_labels(context.models.labels),
            statuses=self._capture_statuses(context.models.statuses),
            characters=characters,
            outline=outline,
            world=self._merge_world_extensions(
                self._capture_world(context.models.world), baseline.world
            ),
            plots=self._merge_plot_extensions(
                self._capture_plots(context.models.plots), baseline.plots
            ),
            revisions=self._capture_revisions(context.models.outline),
            settings_source=context.settings.save(protocol=0),
            plugin_files=tuple(
                PreservedProjectFile(path, content, "plugin-owned")
                for path, content in context.models.plugin_data.project_files()
            ),
            unknown_files=baseline.unknown_files,
            issues=baseline.issues,
            structured_metadata=baseline.structured_metadata,
            source_files=baseline.source_files,
        )

    @staticmethod
    def moves(
        before: CanonicalProject,
        after: CanonicalProject,
    ) -> Tuple[Tuple[str, str], ...]:
        old_paths = {
            ("character", item.id): item.source_path
            for item in before.characters
        }
        old_paths.update({
            ("outline", item.id): item.source_path
            for item in before.documents()
        })
        new_paths = {
            ("character", item.id): item.source_path
            for item in after.characters
        }
        new_paths.update({
            ("outline", item.id): item.source_path
            for item in after.documents()
        })
        return tuple(
            (old_path, new_paths[key])
            for key, old_path in old_paths.items()
            if old_path and new_paths.get(key) and old_path != new_paths[key]
        )

    @staticmethod
    def _hydrate_settings(project, settings) -> None:
        if project.settings_source is not None:
            source = project.settings_source
            if isinstance(source, bytes):
                source = source.decode("utf-8")
            settings.load(source, fromString=True, protocol=0)
        settings.saveToZip = project.zipped
        settings.defaultTextType = "md"

    @staticmethod
    def _hydrate_flat(project, model) -> None:
        metadata = {item.name: item.value for item in project.metadata}
        summary = {item.name: item.value for item in project.summary}
        model.appendRow([
            QStandardItem(metadata.get(name, "")) for name in PROJECT_METADATA
        ])
        model.appendRow([
            QStandardItem(summary.get(name, "")) for name in PROJECT_SUMMARY
        ])

    @staticmethod
    def _hydrate_labels(project, model) -> None:
        model.appendRow(QStandardItem(""))
        for label in project.labels:
            item = QStandardItem(label.name)
            if label.color:
                item.setIcon(iconFromColorString(label.color))
            model.appendRow(item)

    @staticmethod
    def _hydrate_statuses(project, model) -> None:
        model.appendRow(QStandardItem(""))
        for status in project.statuses:
            model.appendRow(QStandardItem(status))

    @staticmethod
    def _hydrate_characters(project, model) -> None:
        for record in project.characters:
            character = model.addCharacter()
            character.lastPath = record.source_path
            for item in record.fields:
                field = CHARACTER_FIELD_TO_ENUM.get(item.name)
                if field is not None:
                    model.setData(character.index(field.value), item.value)
            if record.color:
                character.setColor(QColor(record.color))
            for item in record.custom_fields:
                character.infos.append(CharacterInfo(
                    character, item.name, item.value
                ))

    @staticmethod
    def _hydrate_plots(project, model) -> None:
        for record in project.plots:
            row = [QStandardItem("") for _unused in Plot]
            for item in record.fields:
                field = Plot.__members__.get(item.name)
                if field is not None:
                    row[field.value] = QStandardItem(item.value)
            characters = QStandardItem()
            for character_id in record.character_ids:
                characters.appendRow(QStandardItem(character_id))
            row[Plot.characters] = characters
            steps = QStandardItem()
            for record_step in record.steps:
                step = [QStandardItem("") for _unused in PlotStep]
                for item in record_step.fields:
                    field = PlotStep.__members__.get(item.name)
                    if field is not None:
                        step[field.value] = QStandardItem(item.value)
                steps.appendRow(step)
            row[Plot.steps] = steps
            model.appendRow(row)

    def _hydrate_world(self, project, model) -> None:
        for record in project.world:
            model.appendRow(self._world_row(record))

    def _world_row(self, record) -> List[QStandardItem]:
        row = [QStandardItem("") for _unused in World]
        for item in record.fields:
            field = World.__members__.get(item.name)
            if field is not None:
                row[field.value] = QStandardItem(item.value)
        for child in record.children:
            row[0].appendRow(self._world_row(child))
        return row

    @staticmethod
    def _hydrate_outline(project, model) -> None:
        revisions = {}
        for revision in project.revisions:
            revisions.setdefault(revision.document_id, []).append(revision)

        def append(record, parent):
            item = outlineItem(
                parent=parent,
                ID=record.id,
                title=record.title,
                _type=(
                    "folder" if record.kind == "folder" else "md"
                ),
            )
            item._lastPath = record.source_path
            for value in record.metadata:
                field = Outline.__members__.get(value.name)
                if field is not None and field not in (
                    Outline.ID, Outline.title, Outline.type, Outline.text
                ):
                    item.setData(field, str(value.value))
            text = record.text
            if record.kind == "html":
                text = HTML2PlainText(text)
            if record.kind in ("txt", "t2t", "html"):
                item.setData(Outline.type, "md")
            item.setData(Outline.text, text)
            for revision in revisions.get(record.id, ()):  # no UI inference
                item.appendRevision(revision.timestamp, revision.text)
            for child in record.children:
                append(child, item)

        with model.batchWordCountUpdates():
            for record in project.outline:
                append(record, model.rootItem)
        model.rootItem.checkIDs()

    @staticmethod
    def _capture_flat_row(model, row, names, baseline):
        owned = set(names)
        values = {}
        for column, name in enumerate(names):
            item = model.item(row, column)
            values[name] = item.text().strip() if item is not None else ""
        result = []
        emitted = set()
        for item in baseline:
            if item.name not in owned:
                result.append(item)
            elif item.name not in emitted and values[item.name]:
                result.append(MetadataField(item.name, values[item.name]))
                emitted.add(item.name)
        for name in names:
            if name not in emitted and values[name]:
                result.append(MetadataField(name, values[name]))
        return tuple(result)

    @staticmethod
    def _capture_labels(model) -> Tuple[LabelRecord, ...]:
        result = []
        for row in range(1, model.rowCount()):
            index = model.index(row, 0)
            name = str(model.data(index) or "")
            if not name:
                continue
            decoration = model.data(index, Qt.DecorationRole)
            color = ""
            if decoration is not None:
                color = iconColor(decoration).name(QColor.HexRgb)
                if color == "#ff000000":
                    color = "#00000000"
            result.append(LabelRecord(name, color))
        return tuple(result)

    @staticmethod
    def _capture_statuses(model) -> Tuple[str, ...]:
        return tuple(
            str(model.data(model.index(row, 0)))
            for row in range(1, model.rowCount())
            if model.data(model.index(row, 0))
        )

    def _capture_characters(self, model) -> Tuple[CharacterRecord, ...]:
        records = []
        for character in model.characters:
            fields = []
            for name, enum_value in CHARACTER_FIELD_TO_ENUM.items():
                value = str(model.data(character.index(enum_value.value)) or "").strip()
                if value:
                    fields.append(MetadataField(name, value))
            custom = tuple(
                MetadataField(str(item.description), str(item.value))
                for item in character.infos
            )
            path = posixpath.join(
                "characters",
                "{}-{}.txt".format(
                    character.ID(), self._slugify(character.name())
                ),
            )
            records.append(CharacterRecord(
                id=str(character.ID() or ""),
                name=str(character.name() or ""),
                fields=tuple(fields),
                custom_fields=custom,
                color=character.color().name(QColor.HexRgb),
                source_path=path,
            ))
        return tuple(records)

    def _capture_outline(self, model) -> Tuple[OutlineDocument, ...]:
        def capture(item, parent_path):
            siblings = item.parent().children()
            duplicate = [s.title() for s in siblings].count(item.title()) > 1
            title = "{}-{}".format(item.title(), item.ID()) if duplicate else item.title()
            basename = "{}-{}".format(
                str(item.row()).zfill(len(str(len(siblings)))),
                self._slugify(title),
            )
            item_path = posixpath.join(parent_path, basename)
            source_path = (
                posixpath.join(item_path, "folder.txt")
                if item.type() == "folder"
                else item_path + ".md"
            )
            metadata = []
            excluded = {
                Outline.wordCount, Outline.charCount, Outline.goal,
                Outline.goalPercentage, Outline.revisions, Outline.text,
            }
            for attribute in Outline:
                if attribute in excluded:
                    continue
                value = item.data(attribute)
                if value or attribute is Outline.compile:
                    metadata.append(MetadataField(attribute.name, str(value)))
            return OutlineDocument(
                id=str(item.ID() or ""),
                title=str(item.title() or ""),
                kind=str(item.type() or "md"),
                text=str(item.data(Outline.text) or ""),
                metadata=tuple(metadata),
                children=tuple(
                    capture(child, item_path) for child in item.children()
                ),
                source_path=source_path,
            )

        return tuple(
            capture(child, "outline")
            for child in model.rootItem.children()
        )

    def _capture_world(self, model) -> Tuple[WorldRecord, ...]:
        def capture(parent=QModelIndex()):
            records = []
            for row in range(model.rowCount(parent)):
                fields = []
                for attribute in World:
                    value = model.data(model.index(row, attribute.value, parent))
                    if value:
                        fields.append(MetadataField(attribute.name, str(value)))
                name_index = model.index(row, World.name, parent)
                records.append(WorldRecord(
                    tuple(fields), tuple(capture(name_index))
                ))
            return records

        return tuple(capture())

    @staticmethod
    def _capture_plots(model) -> Tuple[PlotRecord, ...]:
        records = []
        for row_number in range(model.rowCount()):
            fields = []
            for attribute in Plot:
                if attribute in (Plot.characters, Plot.steps):
                    continue
                value = model.data(model.index(row_number, attribute.value))
                if value:
                    fields.append(MetadataField(attribute.name, str(value)))
            character_index = model.index(row_number, Plot.characters)
            character_ids = tuple(
                str(model.data(model.index(row, 0, character_index)) or "")
                for row in range(model.rowCount(character_index))
            )
            step_index = model.index(row_number, Plot.steps)
            steps = []
            for step_row in range(model.rowCount(step_index)):
                step_fields = []
                for attribute in PlotStep:
                    value = model.data(model.index(
                        step_row, attribute.value, step_index
                    ))
                    if value not in (None, ""):
                        step_fields.append(MetadataField(
                            attribute.name, str(value)
                        ))
                steps.append(PlotStepRecord(tuple(step_fields)))
            records.append(PlotRecord(
                tuple(fields), character_ids, tuple(steps)
            ))
        return tuple(records)

    @staticmethod
    def _capture_revisions(model) -> Tuple[RevisionRecord, ...]:
        revisions = []
        def collect(item):
            for timestamp, text in item.revisions():
                revisions.append(RevisionRecord(
                    str(item.ID() or ""), str(timestamp), str(text)
                ))
            for child in item.children():
                collect(child)
        for child in model.rootItem.children():
            collect(child)
        return tuple(revisions)

    def _merge_outline_extensions(
        self, captured, baseline, preserve_paths=False
    ):
        previous = {item.id: item for item in self._walk_outline(baseline)}

        def merge(document):
            old = previous.get(document.id)
            if preserve_paths and old is not None:
                metadata = self._merge_v2_outline_metadata(
                    document.metadata, old
                )
            else:
                metadata = list(document.metadata)
                known_names = {item.name for item in metadata}
                if old is not None:
                    metadata.extend(
                        item for item in old.metadata
                        if item.name not in Outline.__members__
                        and item.name not in known_names
                    )
            return replace(
                document,
                source_path=(
                    old.source_path if old is not None
                    else ""
                ) if preserve_paths else document.source_path,
                kind=(
                    old.kind
                    if preserve_paths and old is not None
                    else document.kind
                ),
                source_format=(
                    old.source_format
                    if preserve_paths and old is not None
                    else document.source_format
                ),
                raw_source=(
                    old.raw_source
                    if preserve_paths and old is not None
                    else document.raw_source
                ),
                structured_metadata=(
                    old.structured_metadata
                    if preserve_paths and old is not None
                    else document.structured_metadata
                ),
                metadata=tuple(metadata),
                children=tuple(merge(child) for child in document.children),
            )
        return tuple(merge(item) for item in captured)

    @staticmethod
    def _merge_v2_outline_metadata(captured, old):
        """Preserve untouched v2 metadata spelling, order, and raw source."""

        identity_fields = {"ID", "title", "type"}
        captured_fields = [
            item for item in captured if item.name not in identity_fields
        ]
        captured_by_name = {item.name: item for item in captured_fields}
        handled = set()
        metadata = []
        for previous in old.metadata:
            if previous.name in identity_fields:
                if old.source_format == "mmd":
                    metadata.append(previous)
                continue
            current = captured_by_name.get(previous.name)
            if current is None:
                if previous.name not in Outline.__members__:
                    metadata.append(previous)
                continue
            if LegacyApplicationModelAdapter._metadata_equivalent(
                previous, current
            ):
                metadata.append(previous)
            elif previous.name not in handled:
                metadata.append(current)
            handled.add(previous.name)

        for current in captured_fields:
            if current.name in handled:
                continue
            # Compile is checked by default in the legacy live model. Its
            # absence in v2 therefore means the same thing as Qt.Checked.
            if (
                current.name == "compile"
                and LegacyApplicationModelAdapter._truth_value(current.value)
                is True
            ):
                continue
            metadata.append(current)
            handled.add(current.name)
        return metadata

    @staticmethod
    def _metadata_equivalent(previous, current):
        if previous.name != current.name:
            return False
        if previous.name == "compile":
            return (
                LegacyApplicationModelAdapter._truth_value(previous.value)
                == LegacyApplicationModelAdapter._truth_value(current.value)
            )
        return previous.value == current.value

    @staticmethod
    def _truth_value(value):
        normalized = str(value).strip().casefold()
        if normalized in {"1", "2", "true", "yes", "on"}:
            return True
        if normalized in {"", "0", "false", "no", "off"}:
            return False
        return None

    @staticmethod
    def _walk_outline(records):
        for record in records:
            yield record
            for child in record.children:
                yield from LegacyApplicationModelAdapter._walk_outline((child,))

    def _merge_world_extensions(self, captured, baseline):
        known = set(World.__members__)

        def keyed(records):
            return {
                record.value("ID"): record for record in records
                if record.value("ID")
            }

        def merge(records, old_records):
            old_by_id = keyed(old_records)
            result = []
            for record in records:
                old = old_by_id.get(record.value("ID"))
                fields = list(record.fields)
                names = {item.name for item in fields}
                if old is not None:
                    fields.extend(
                        item for item in old.fields
                        if item.name not in known and item.name not in names
                    )
                    children = merge(record.children, old.children)
                else:
                    children = record.children
                result.append(WorldRecord(tuple(fields), tuple(children)))
            return tuple(result)

        return merge(captured, baseline)

    @staticmethod
    def _merge_plot_extensions(captured, baseline):
        known_plot = set(Plot.__members__)
        known_step = set(PlotStep.__members__)
        old_by_id = {
            record.value("ID"): record for record in baseline
            if record.value("ID")
        }
        result = []
        for record in captured:
            old = old_by_id.get(record.value("ID"))
            fields = list(record.fields)
            if old is not None:
                names = {item.name for item in fields}
                fields.extend(
                    item for item in old.fields
                    if item.name not in known_plot and item.name not in names
                )
            old_steps = {
                step.value("ID"): step for step in old.steps
                if step.value("ID")
            } if old is not None else {}
            steps = []
            for step in record.steps:
                old_step = old_steps.get(step.value("ID"))
                step_fields = list(step.fields)
                if old_step is not None:
                    names = {item.name for item in step_fields}
                    step_fields.extend(
                        item for item in old_step.fields
                        if item.name not in known_step and item.name not in names
                    )
                steps.append(PlotStepRecord(tuple(step_fields)))
            result.append(PlotRecord(
                tuple(fields), record.character_ids, tuple(steps)
            ))
        return tuple(result)

    @staticmethod
    def _slugify(name: str) -> str:
        valid = string.ascii_letters + string.digits
        return "".join(
            character if character in valid
            else "_" if character in string.whitespace
            else "-"
            for character in str(name)
        )
