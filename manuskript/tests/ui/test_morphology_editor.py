from PyQt5.QtWidgets import QTableWidgetItem

from manuskript.domain.morphology import (
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.linguistics import first_party_morphology_providers
from manuskript.ui.morphology_editor import (
    MorphologyParadigmDialog,
    default_name_profile,
)


def _ukrainian_profile():
    return MorphologyProfile(
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


def test_default_compound_profile_keeps_each_name_component_explicit():
    profile = default_name_profile(
        "Олена Ковальська", "uk.personal-names"
    )

    assert tuple(item.lemma for item in profile.components) == (
        "Олена", "Ковальська"
    )
    assert tuple(item.role for item in profile.components) == (
        "given-name", "surname"
    )


def test_paradigm_dialog_previews_compound_forms_and_exposes_accessible_tables():
    dialog = MorphologyParadigmDialog(
        _ukrainian_profile(),
        first_party_morphology_providers(),
        "Олена Ковальська",
    )

    preview = {
        dialog.previewTable.item(row, 0).text():
            dialog.previewTable.item(row, 1).text()
        for row in range(dialog.previewTable.rowCount())
    }

    assert preview["Genitive"] == "Олени Ковальської"
    assert preview["Instrumental"] == "Оленою Ковальською"
    assert dialog.providerCombo.accessibleName() == "Language provider"
    assert dialog.formsTable.accessibleName() == (
        "Generated forms and author overrides"
    )
    assert dialog.previewTable.accessibleName() == (
        "Generated compound-name forms"
    )
    assert dialog.validationLabel.accessibleName() == "Morphology validation"
    assert dialog.validationLabel.text() == "Configuration is valid."


def test_paradigm_dialog_persists_an_author_override_on_one_component():
    dialog = MorphologyParadigmDialog(
        _ukrainian_profile(),
        first_party_morphology_providers(),
        "Олена Ковальська",
    )
    genitive_row = next(
        row for row in range(dialog.formsTable.rowCount())
        if dialog.formsTable.item(row, 0).data(256) == "genitive"
    )

    dialog.formsTable.setItem(
        genitive_row, 2, QTableWidgetItem("Олени (author form)")
    )

    assert dict(dialog.profile.components[0].overrides)["genitive"] == (
        "Олени (author form)"
    )
    assert dialog.previewTable.item(genitive_row, 1).text().startswith(
        "Олени (author form)"
    )
