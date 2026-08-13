import pytest

from manuskript.domain.canonical_project import EntityRecord, OutlineDocument
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyIndex,
    MorphologyProfile,
    normalize_language_tag,
)
from manuskript.linguistics import (
    MorphologyPackError,
    first_party_morphology_schemas,
    load_morphology_schemas,
    parse_morphology_pack,
)


def _component(role, lemma, gender="feminine", overrides=()):
    return MorphologyComponent(
        role,
        lemma,
        (("gender", gender),),
        overrides,
    )


def _entity(identifier, title, profile, aliases=()):
    return EntityRecord(
        OutlineDocument(
            identifier,
            title,
            "entity",
            "",
            source_path="Characters/{}.md".format(title),
        ),
        "character",
        aliases,
        profile.apply_to(()),
    )


def test_profile_stores_language_schema_features_and_overrides_as_data():
    profile = MorphologyProfile(
        "uk",
        "uk.personal-names",
        (_component("given-name", "Олена"),),
    )
    entity = _entity("olena", "Олена", profile)

    reopened = MorphologyProfile.from_entity(entity)

    assert reopened == profile
    assert entity.metadata[0].value["language"] == "uk"
    assert entity.metadata[0].value["schema"] == "uk.personal-names"
    assert entity.metadata[0].value["components"][0]["lemma"] == "Олена"


def test_development_provider_metadata_is_not_a_public_format():
    assert MorphologyProfile.from_value({
        "version": 1,
        "provider": "uk.personal-names",
        "components": [{"role": "name", "lemma": "Олена"}],
    }) is None


@pytest.mark.parametrize(
    "entered, normalized",
    (("tlh_001", "tlh-001"), ("x_code_001", "x-code-001"), ("qaa", "qaa")),
)
def test_language_tags_accept_registered_and_private_namespaces(entered, normalized):
    assert normalize_language_tag(entered) == normalized


def test_ukrainian_pack_generates_reviewable_compound_name_forms():
    schemas = first_party_morphology_schemas()
    profile = MorphologyProfile(
        "uk",
        "uk.personal-names",
        (
            _component("given-name", "Олена"),
            _component("surname", "Ковальська"),
        ),
    )

    forms = {form.key: form.text for form in schemas.generate(profile)}

    assert forms["nominative"] == "Олена Ковальська"
    assert forms["genitive"] == "Олени Ковальської"
    assert forms["dative"] == "Олені Ковальській"
    assert forms["instrumental"] == "Оленою Ковальською"
    assert forms["vocative"] == "Олено Ковальська"


def test_russian_pack_supports_soft_sign_and_author_override():
    schemas = first_party_morphology_schemas()
    profile = MorphologyProfile(
        "ru",
        "ru.personal-names",
        (
            _component(
                "given-name",
                "Игорь",
                "masculine",
                (("instrumental", "Игорем (preferred)"),),
            ),
        ),
    )

    forms = {form.key: form.text for form in schemas.generate(profile)}

    assert forms["genitive"] == "Игоря"
    assert forms["instrumental"] == "Игорем (preferred)"
    assert schemas.analyse(profile, "Игорем (preferred)")[0].key == "instrumental"


@pytest.mark.parametrize(
    "lemma, plural",
    (("mouse", "mice"), ("goose", "geese"), ("foot", "feet"), ("city", "cities")),
)
def test_english_is_a_first_party_pack_not_an_engine_special_case(lemma, plural):
    schemas = first_party_morphology_schemas()
    profile = MorphologyProfile(
        "en",
        "en.nominals",
        (MorphologyComponent("noun", lemma, (("inflection", "regular"),)),),
    )

    assert {form.key: form.text for form in schemas.generate(profile)}["plural"] == plural


def test_missing_schema_preserves_and_indexes_opaque_manual_forms():
    schemas = first_party_morphology_schemas()
    profile = MorphologyProfile(
        "x-velari",
        "",
        (MorphologyComponent(
            "speaker-name",
            "Tara",
            (("social-class", "river"),),
            (("addressive", "Tarai"),),
        ),),
    )
    entity = _entity("tara", "Tara", profile)
    index = MorphologyIndex(schemas)
    index.rebuild((entity,))

    issues = schemas.validate(profile)

    assert issues and not issues[0].blocking
    assert schemas.generate(profile)[0].text == "Tarai"
    assert index.lookup("tarai")[0].entity_id == "tara"
    assert MorphologyProfile.from_entity(entity) == profile


def test_fictional_pack_is_discovered_from_a_dropped_in_xml_file(tmp_path):
    source = """\
<morphology-pack id="x.velari.nouns" label="Velari nouns" language="x-velari" version="3">
  <components default-role="noun"><role id="noun" label="Noun"/></components>
  <forms><form id="one" label="One"/><form id="many" label="Many"/></forms>
  <paradigms><paradigm id="plural" roles="noun"><surface form="many" append="-ir"/></paradigm></paradigms>
</morphology-pack>
"""
    filename = tmp_path / "velari.morphology.xml"
    filename.write_text(source, encoding="utf-8")

    schemas = load_morphology_schemas((tmp_path,), strict=True)
    profile = MorphologyProfile(
        "x-velari", "x.velari.nouns", (MorphologyComponent("noun", "tal"),)
    )

    assert schemas.get("x.velari.nouns").version == "3"
    assert {form.key: form.text for form in schemas.generate(profile)} == {
        "one": "tal", "many": "tal-ir"
    }


def test_pack_loader_rejects_executable_or_malformed_content():
    with pytest.raises(MorphologyPackError):
        parse_morphology_pack("<script>open('/tmp/leak')</script>")
