from manuskript.models.characterModel import characterModel


def test_character_info_rows_are_managed_without_ui_dependencies():
    model = characterModel(None)
    character = model.addCharacter(name="Alice")

    assert model.addCharacterInfo(character.ID(), "Age", "32")
    assert model.addCharacterInfo(character.ID(), "Role", "Protagonist")
    assert [(info.description, info.value) for info in character.infos] == [
        ("Age", "32"),
        ("Role", "Protagonist"),
    ]

    assert model.removeCharacterInfo(character.ID(), {0})
    assert [(info.description, info.value) for info in character.infos] == [
        ("Role", "Protagonist"),
    ]


def test_character_info_operations_reject_unknown_character():
    model = characterModel(None)

    assert not model.addCharacterInfo("unknown", "Age", "32")
    assert not model.removeCharacterInfo("unknown", {0})
