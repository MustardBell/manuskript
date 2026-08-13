from dataclasses import replace

from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    EntityRecord,
    MetadataField,
    PlotRecord,
    PlotStepRecord,
    StructuredMetadataField,
    WorldRecord,
)
from manuskript.services.legacy_entity_adapter import LegacyEntityAdapter


def test_legacy_story_records_project_into_generic_entities_without_collision():
    project = CanonicalProject(
        format_version=1,
        characters=(CharacterRecord(
            "1",
            "Mara Vale",
            fields=(MetadataField("notes", "Character notes."),),
            custom_fields=(MetadataField("Aliases", "Mara\nMs Vale"),),
            source_path="characters/1-mara-vale.txt",
        ),),
        world=(WorldRecord((
            MetadataField("ID", "1"),
            MetadataField("name", "Vienna"),
            MetadataField("description", "Place notes."),
        )),),
        plots=(PlotRecord((
            MetadataField("ID", "1"),
            MetadataField("name", "Forged letter"),
            MetadataField("description", "Plot notes."),
        )),),
    )

    entities = LegacyEntityAdapter().project(project)

    assert tuple(entity.id for entity in entities) == (
        "project:summary",
        "legacy:character:1",
        "legacy:world:1",
        "legacy:plot:1",
    )
    assert tuple(entity.type for entity in entities) == (
        "project", "character", "world", "plot",
    )
    assert entities[1].aliases == ("Mara", "Ms Vale")
    assert entities[1].document.text == "Character notes."
    assert entities[2].document.text == "Place notes."


def test_projected_character_edits_write_back_without_losing_extensions():
    project = CanonicalProject(
        format_version=1,
        characters=(CharacterRecord(
            "17",
            "Олена Коваль",
            fields=(
                MetadataField("Importance", "2"),
                MetadataField("Notes", "Old notes."),
            ),
            custom_fields=(
                MetadataField("Language", "uk"),
                MetadataField("Alias", "Лена"),
            ),
            color="#336699",
        ),),
    )
    adapter = LegacyEntityAdapter()
    entity = adapter.project(project)[1]
    entity = EntityRecord(
        document=replace(
            entity.document, title="Олена Вовк", text="New notes."
        ),
        entity_type=entity.type,
        aliases=("Лена", "Оленка"),
        metadata=tuple(
            StructuredMetadataField(
                item.name,
                "1" if item.name == "Importance" else item.value,
            )
            for item in entity.metadata
        ),
    )

    updated = adapter.update(project, entity)
    character = updated.characters[0]

    assert character.name == "Олена Вовк"
    assert character.value("Importance") == "1"
    assert character.value("Notes") == "New notes."
    assert character.color == "#336699"
    assert MetadataField("Language", "uk") in character.custom_fields
    assert MetadataField("Aliases", "Лена\nОленка") in (
        character.custom_fields
    )


def test_summary_world_and_plot_edits_write_back_to_their_legacy_records():
    project = CanonicalProject(
        format_version=1,
        metadata=(MetadataField("Title", "Old title"),),
        summary=(
            MetadataField("Sentence", "Old sentence"),
            MetadataField("Full", "Old full summary"),
        ),
        world=(WorldRecord((
            MetadataField("ID", "4"),
            MetadataField("name", "Old place"),
            MetadataField("description", "Old description"),
            MetadataField("passion", "Old passion"),
            MetadataField("future-field", "preserved"),
        )),),
        plots=(PlotRecord(
            (
                MetadataField("ID", "5"),
                MetadataField("name", "Old plot"),
                MetadataField("description", "Old plot description"),
            ),
            ("17",),
            (PlotStepRecord((MetadataField("name", "Turn"),)),),
        ),),
    )
    adapter = LegacyEntityAdapter()
    entities = {item.id: item for item in adapter.project(project)}

    summary = replace(
        entities["project:summary"],
        document=replace(
            entities["project:summary"].document,
            title="New title",
            text="New full summary",
        ),
        metadata=(StructuredMetadataField(
            "summary.Sentence", "New sentence"
        ),),
    )
    project = adapter.update(project, summary)
    world = entities["legacy:world:4"]
    world = replace(
        world,
        document=replace(
            world.document, title="New place", text="New description"
        ),
        metadata=tuple(
            StructuredMetadataField(
                item.name,
                "New passion" if item.name == "passion" else item.value,
            )
            for item in world.metadata
        ),
    )
    project = adapter.update(project, world)
    plot = entities["legacy:plot:5"]
    plot = replace(
        plot,
        document=replace(
            plot.document, title="New plot", text="New plot description"
        ),
    )
    project = adapter.update(project, plot)

    assert project.metadata[0] == MetadataField("Title", "New title")
    assert project.summary == (
        MetadataField("Sentence", "New sentence"),
        MetadataField("Full", "New full summary"),
    )
    assert project.world[0].value("name") == "New place"
    assert project.world[0].value("description") == "New description"
    assert project.world[0].value("passion") == "New passion"
    assert project.world[0].value("future-field") == "preserved"
    assert project.plots[0].value("name") == "New plot"
    assert project.plots[0].character_ids == ("17",)
    assert project.plots[0].steps[0].value("name") == "Turn"
