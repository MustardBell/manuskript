from pathlib import Path
from dataclasses import replace

import yaml

from manuskript.domain.markdown_dsl import render_wikilinks_as_markdown
from manuskript.domain.reference_index import ReferenceDocument, ReferenceIndex
from manuskript.load_save.frontmatter import parse_frontmatter
from manuskript.load_save.version_2_codec import Version2ProjectCodec


FIXTURE = Path(__file__).parents[1] / "fixtures" / "obsidian_vault"


def _files():
    return {
        path.relative_to(FIXTURE).as_posix(): path.read_text(encoding="utf-8")
        for path in FIXTURE.rglob("*") if path.is_file()
    }


def test_shared_vault_resolves_wikilinks_aliases_and_preserves_foreign_files():
    source = _files()
    codec = Version2ProjectCodec()

    project = codec.decode(source)
    index = ReferenceIndex()
    index.rebuild(tuple(
        ReferenceDocument(
            document.id,
            document.source_path,
            document.title,
            document.text,
            next((
                entity.aliases for entity in project.entities
                if entity.id == document.id
            ), ()),
        )
        for document in project.documents()
    ))

    assert not [issue for issue in codec.validate(project) if issue.severity == "error"]
    assert project.entities[0].aliases == ("Mara", "Ms Vale")
    assert index.resolve("Characters/Mara Vale")[1].id == "entity-mara"
    assert index.resolve("Mara")[1].id == "entity-mara"
    assert index.backlinks("entity-mara")[0].source_document_id == "scene-opening"
    assert project.file("Notes/Obsidian-only.md").content == source[
        "Notes/Obsidian-only.md"
    ]
    assert project.file(".obsidian/app.json").content == source[
        ".obsidian/app.json"
    ]
    assert dict(codec.encode(project).files) == source


def test_obsidian_alias_and_body_edits_remain_loadable_and_yaml_is_plain():
    source = _files()
    entity_path = "Characters/Mara Vale.md"
    source[entity_path] = source[entity_path].replace(
        "  - Ms Vale\n", "  - Ms Vale\n  - M. Vale\n"
    ).replace(
        "Character notes edited by either application.",
        "Notes changed in Obsidian.",
    )

    project = Version2ProjectCodec().decode(source)
    entity = project.entities[0]
    frontmatter = parse_frontmatter(source[entity_path])

    assert yaml.safe_load(source["project.yaml"])["manuskript"]["format"] == 2
    assert frontmatter.metadata["aliases"] == ["Mara", "Ms Vale", "M. Vale"]
    assert entity.aliases == ("Mara", "Ms Vale", "M. Vale")
    assert entity.document.text == "Notes changed in Obsidian.\n"
    assert render_wikilinks_as_markdown(
        "[[Characters/Mara Vale|Mara]]"
    ) == "[Mara](manuskript:Characters/Mara%20Vale)"


def test_manuskript_entity_edits_preserve_obsidian_owned_frontmatter():
    codec = Version2ProjectCodec()
    project = codec.decode(_files())
    entity = project.entities[0]
    updated = replace(
        entity,
        aliases=entity.aliases + ("M. Vale",),
        document=replace(
            entity.document, text="Notes changed in Manuskript.\n"
        ),
    )
    changed_project = replace(project, entities=(updated,))

    changed_files = dict(codec.encode(changed_project).files)
    parsed = parse_frontmatter(changed_files[entity.document.source_path])

    assert parsed.metadata["tags"] == ["character"]
    assert parsed.metadata["aliases"] == ["Mara", "Ms Vale", "M. Vale"]
    assert parsed.body == "Notes changed in Manuskript.\n"
