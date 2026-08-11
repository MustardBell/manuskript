import pytest

from manuskript.domain.canonical_project import EntityRecord, OutlineDocument
from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyIndex,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_providers


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


def test_morphology_profile_is_inspectable_structured_metadata():
    profile = MorphologyProfile(
        "uk.personal-names",
        (_component("given-name", "Олена"),),
    )
    entity = _entity("olena", "Олена", profile)

    reopened = MorphologyProfile.from_entity(entity)

    assert reopened == profile
    assert entity.metadata[0].value["provider"] == "uk.personal-names"
    assert entity.metadata[0].value["components"][0]["lemma"] == "Олена"


def test_ukrainian_provider_generates_reviewable_compound_name_forms():
    providers = first_party_morphology_providers()
    profile = MorphologyProfile(
        "uk.personal-names",
        (
            _component("given-name", "Олена"),
            _component("surname", "Ковальська"),
        ),
    )

    forms = {form.key: form.text for form in providers.generate(profile)}

    assert forms["nominative"] == "Олена Ковальська"
    assert forms["genitive"] == "Олени Ковальської"
    assert forms["dative"] == "Олені Ковальській"
    assert forms["instrumental"] == "Оленою Ковальською"
    assert forms["vocative"] == "Олено Ковальська"


def test_russian_provider_supports_soft_sign_and_author_override():
    providers = first_party_morphology_providers()
    profile = MorphologyProfile(
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

    forms = {form.key: form.text for form in providers.generate(profile)}

    assert forms["genitive"] == "Игоря"
    assert forms["instrumental"] == "Игорем (preferred)"
    provider = providers.get("ru.personal-names")
    assert provider.analyse(
        "Игорем (preferred)", profile.components[0]
    )[0].key == "instrumental"


def test_morphology_index_maps_generated_forms_to_stable_entity_identity():
    providers = first_party_morphology_providers()
    profile = MorphologyProfile(
        "uk.personal-names",
        (_component("given-name", "Олена"),),
    )
    index = MorphologyIndex(providers)
    index.rebuild((
        _entity("olena", "Олена", profile, ("Лена",)),
    ))

    generated = index.lookup("  ОЛЕНИ ")

    assert generated[0].entity_id == "olena"
    assert generated[0].source == "generated"
    assert generated[0].form_key == "genitive"
    assert {item.text for item in index.forms_for("olena")} >= {
        "Олена", "Лена", "Олени", "Олені", "Оленою",
    }


def test_missing_provider_leaves_profile_data_intact_but_generates_nothing():
    providers = first_party_morphology_providers()
    profile = MorphologyProfile(
        "plugin.missing",
        (_component("given-name", "Mara"),),
    )

    issues = providers.validate(profile)

    assert providers.generate(profile) == ()
    assert "unavailable" in issues[0].message


def test_provider_extension_point_rejects_incomplete_and_contains_failures():
    providers = first_party_morphology_providers()

    class Incomplete:
        id = "plugin.incomplete"

    with pytest.raises(ValueError, match="implement"):
        providers.register(Incomplete())

    class Broken:
        id = "plugin.broken"
        label = "Broken"
        language = "x-test"
        component_roles = (("name", "Name"),)
        genders = ()

        @staticmethod
        def validate(_component):
            raise RuntimeError("provider defect")

        @staticmethod
        def generate(_component):
            raise RuntimeError("provider defect")

        @staticmethod
        def analyse(_surface, _component):
            return ()

    providers.register(Broken())
    profile = MorphologyProfile(
        Broken.id, (_component("name", "Mara"),)
    )

    assert "provider defect" in providers.validate(profile)[0].message
    assert providers.generate(profile) == ()
