import pytest

from manuskript.domain.canonical_project import (
    EntityRecord,
    OutlineDocument,
)
from manuskript.domain.entity_catalog import (
    EntityCatalog,
    EntitySchema,
    EntitySchemaRegistry,
    first_party_story_entity_schemas,
)
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyIndex,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_schemas


def _entity(identifier, title, path, aliases=(), entity_type="character"):
    return EntityRecord(
        OutlineDocument(
            identifier, title, "entity", "", source_path=path
        ),
        entity_type,
        aliases,
    )


def test_exact_title_and_alias_matching_is_explicit_and_ambiguity_survives():
    catalog = EntityCatalog()
    catalog.replace((
        _entity("mara", "Mara Vale", "Characters/Mara Vale.md", ("Mara",)),
        _entity("city", "Mara", "Places/Mara.md", entity_type="place"),
    ))

    matches = catalog.exact_matches("  MARA ")
    choices = catalog.reference_choices("Mara Vale")

    assert tuple(entity.id for entity in matches) == ("mara", "city")
    assert choices[0].entity_id == "mara"
    assert choices[0].exact_match
    assert choices[0].target == "Characters/Mara Vale"
    assert not choices[1].exact_match


def test_native_entity_creation_uses_injected_schema_and_stable_identity():
    identifiers = iter(("entity-1", "entity-2"))
    catalog = EntityCatalog(
        first_party_story_entity_schemas(),
        id_factory=lambda: next(identifiers),
    )
    catalog.replace((), writable=True)

    first = catalog.create("character", "Олена Коваль", ("Олена", "Олена"))
    second = catalog.create("character", "Олена Коваль")

    assert first.id == "entity-1"
    assert first.type == "character"
    assert first.aliases == ("Олена",)
    assert first.document.source_path == "Characters/Олена Коваль.md"
    assert second.document.source_path == "Characters/Олена Коваль-2.md"


def test_read_only_legacy_catalog_cannot_create_native_entities():
    catalog = EntityCatalog(first_party_story_entity_schemas())
    catalog.replace((), writable=False)

    with pytest.raises(PermissionError, match="Format 2"):
        catalog.create("character", "Mara")


@pytest.mark.parametrize(
    "directory",
    (
        "../Characters",
        "/Characters",
        "Characters/../Elsewhere",
        "C:Characters",
    ),
)
def test_entity_schema_rejects_directories_outside_the_project(directory):
    with pytest.raises(ValueError, match="safe relative paths"):
        EntitySchemaRegistry((EntitySchema("character", "Character", directory),))


def test_surface_scanner_is_exact_boundary_aware_and_does_not_relink_markup():
    catalog = EntityCatalog()
    catalog.replace((
        _entity("mara", "Mara", "Characters/Mara.md"),
        _entity("mara-vale", "Mara Vale", "Characters/Mara Vale.md"),
        _entity("other-mara", "Other", "Places/Other.md", ("Mara",), "place"),
    ))
    source = (
        "Mara Vale met Mara. Amaranth is unrelated. "
        "[[Characters/Mara|Mara]] and `Mara` are already excluded."
    )

    matches = catalog.scan(source)

    assert tuple(match.surface for match in matches) == ("Mara Vale", "Mara")
    assert matches[0].entity_ids == ("mara-vale",)
    assert matches[0].is_unique
    assert matches[1].entity_ids == ("mara", "other-mara")
    assert matches[1].is_ambiguous


def test_entity_update_keeps_identity_and_address_while_editing_semantics():
    catalog = EntityCatalog()
    original = _entity(
        "mara", "Mara Vale", "Characters/Mara Vale.md", ("Mara",)
    )
    catalog.replace((original,), writable=True)

    updated = catalog.update(
        "mara",
        title="Mara Vane",
        aliases=("Mara", "Ms Vane"),
        text="Updated notes.",
    )

    assert updated.id == "mara"
    assert updated.document.source_path == "Characters/Mara Vale.md"
    assert updated.title == "Mara Vane"
    assert updated.aliases == ("Mara", "Ms Vane")
    assert updated.document.text == "Updated notes."


def test_generated_morphology_participates_in_exact_matching_and_scanning():
    index = MorphologyIndex(first_party_morphology_schemas())
    catalog = EntityCatalog(morphology_index=index)
    profile = MorphologyProfile(
        "uk",
        "uk.personal-names",
        (MorphologyComponent(
            "given-name", "Олена", (("gender", "feminine"),)
        ),),
    )
    entity = EntityRecord(
        OutlineDocument(
            "olena", "Олена", "entity", "",
            source_path="Characters/Олена.md",
        ),
        "character",
        metadata=profile.apply_to(()),
    )
    catalog.replace((entity,))

    assert tuple(item.id for item in catalog.exact_matches("Олени")) == (
        "olena",
    )
    assert catalog.reference_choices("Олені")[0].exact_match
    assert catalog.scan("Я зустрів Олену біля вокзалу.")[0].entity_ids == (
        "olena",
    )
