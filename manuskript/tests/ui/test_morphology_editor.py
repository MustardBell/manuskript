from PyQt5.QtWidgets import QComboBox, QTableWidgetItem

from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_schemas
from manuskript.ui.morphology_editor import (
    MorphologyParadigmDialog,
    default_morphology_profile,
)


def _ukrainian_profile():
    return MorphologyProfile(
        "uk",
        "uk.personal-names",
        (
            MorphologyComponent(
                "given-name", "Олена", (("gender", "feminine"),)
            ),
            MorphologyComponent(
                "surname", "Ковальська", (("gender", "feminine"),)
            ),
        ),
    )


def test_default_profile_does_not_infer_structure_from_an_entity_title():
    profile = default_morphology_profile("Олена Ковальська")

    assert profile.language_tag == "und"
    assert profile.schema_id == ""
    assert profile.components == (MorphologyComponent("", "Олена Ковальська"),)


def test_dialog_builds_features_from_the_pack_and_previews_compound_forms():
    dialog = MorphologyParadigmDialog(
        _ukrainian_profile(),
        first_party_morphology_schemas(),
        "Олена Ковальська",
    )

    preview = {
        dialog.previewTable.item(row, 0).text():
            dialog.previewTable.item(row, 1).text()
        for row in range(dialog.previewTable.rowCount())
    }
    gender = dialog.findChild(QComboBox, "morphologyFeature.gender")

    assert gender is not None
    assert gender.accessibleName() == "Gender"
    assert preview["Genitive"] == "Олени Ковальської"
    assert preview["Instrumental"] == "Оленою Ковальською"
    assert dialog.languageEdit.accessibleName() == "BCP 47 language tag"
    assert dialog.schemaCombo.accessibleName() == "Morphology schema"
    assert dialog.formsTable.accessibleName() == (
        "Generated forms and author overrides"
    )
    assert dialog.validationLabel.text() == "Configuration is valid."


def test_dialog_persists_an_author_override_on_one_component():
    dialog = MorphologyParadigmDialog(
        _ukrainian_profile(),
        first_party_morphology_schemas(),
        "Олена Ковальська",
    )
    genitive_row = next(
        row for row in range(dialog.formsTable.rowCount())
        if dialog.formsTable.item(row, 0).text() == "genitive"
    )

    dialog.formsTable.setItem(
        genitive_row, 3, QTableWidgetItem("Олени (author form)")
    )

    assert dict(dialog.profile.components[0].overrides)["genitive"] == (
        "Олени (author form)"
    )
    assert dialog.previewTable.item(genitive_row, 1).text().startswith(
        "Олени (author form)"
    )


def test_unknown_language_and_schema_remain_manually_editable():
    profile = MorphologyProfile(
        "x-velari",
        "x.velari.missing",
        (MorphologyComponent(
            "honor-name",
            "Tal",
            (("rank", "third"),),
            (("addressive", "Tal-ir"),),
        ),),
    )
    dialog = MorphologyParadigmDialog(
        profile, first_party_morphology_schemas(), "Tal"
    )

    assert dialog.languageEdit.text() == "x-velari"
    assert dialog.roleCombo.currentText() == "honor-name"
    assert dialog.extraAttributes.item(0, 0).text() == "rank"
    assert dialog.formsTable.item(0, 0).text() == "addressive"
    assert dialog.formsTable.item(0, 3).text() == "Tal-ir"
    assert dialog.buttons.button(dialog.buttons.Save).isEnabled()
    assert "unavailable" in dialog.validationLabel.text()
    assert dialog.profile == profile


def test_selecting_a_pack_applies_its_declared_defaults_not_first_choices():
    dialog = MorphologyParadigmDialog(
        None, first_party_morphology_schemas(), "Олена"
    )

    dialog.schemaCombo.setCurrentIndex(
        dialog.schemaCombo.findData("uk.personal-names")
    )

    component = dialog.profile.components[0]
    assert dialog.profile.language_tag == "uk"
    assert component.role == "given-name"
    assert dict(component.attributes) == {"gender": "invariable"}
