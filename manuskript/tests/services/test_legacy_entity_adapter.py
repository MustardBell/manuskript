from manuskript.domain.canonical_project import (
    CanonicalProject,
    CharacterRecord,
    MetadataField,
    PlotRecord,
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
