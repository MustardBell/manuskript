"""The character controller drives a panel, not a window.

It used to take the whole window and reach for twenty of its attributes.
These tests are written the way it works now: it is handed the panel, the
models, and the two services every panel needs, so a test says what it
is driving rather than mocking everything a window can do.
"""

from unittest.mock import MagicMock, call

from manuskript.controllers.character_controller import CharacterController
from manuskript.ui.views.character_panel import CharacterPanelView


def make_controller(confirm=True):
    models = MagicMock()
    panel = CharacterPanelView(
        characters=MagicMock(),
        tabs=MagicMock(),
        info=MagicMock(),
        color_button=MagicMock(),
        pov_checkbox=MagicMock(),
        importance_slider=MagicMock(),
        add_character_button=MagicMock(),
        remove_character_button=MagicMock(),
        add_info_button=MagicMock(),
        remove_info_button=MagicMock(),
        fields=(MagicMock(), MagicMock()),
    )
    navigation = MagicMock()
    dialogs = MagicMock()
    dialogs.translate.side_effect = lambda text: text
    dialogs.confirm.return_value = confirm
    controller = CharacterController(models, panel, navigation, dialogs)
    return controller, models, panel, navigation, dialogs


def test_character_selection_text_handles_multiple_and_empty_selections():
    controller, _models, panel, _nav, _dialogs = make_controller()
    alice = MagicMock()
    alice.name.return_value = "Alice"
    bob = MagicMock()
    bob.name.return_value = "Bob"
    panel.characters.currentCharacters.return_value = [alice, bob]

    assert controller.character_selection_text() == '"Alice", "Bob"'

    panel.characters.currentCharacters.return_value = []
    assert controller.character_selection_text() == ""


def test_delete_characters_removes_each_character_and_clears_pov_references():
    controller, models, panel, _nav, _dialogs = make_controller()
    panel.characters.currentCharacterIDs.return_value = ["alice", "bob"]
    models.outline.findItemsByPOV.side_effect = [
        ["alice-scene"],
        ["bob-scene"],
    ]
    alice_scene = MagicMock()
    bob_scene = MagicMock()
    models.outline.getItemByID.side_effect = {
        "alice-scene": alice_scene,
        "bob-scene": bob_scene,
    }.get

    deleted = controller.delete_characters()

    assert deleted == ["alice", "bob"]
    assert models.characters.removeCharacter.call_args_list == [
        call("alice"),
        call("bob"),
    ]
    alice_scene.resetPOV.assert_called_once_with()
    bob_scene.resetPOV.assert_called_once_with()


def test_delete_characters_respects_cancel():
    controller, models, panel, _nav, _dialogs = make_controller(
        confirm=False
    )
    panel.characters.currentCharacterIDs.return_value = ["alice"]

    deleted = controller.delete_characters()

    assert deleted == []
    models.characters.removeCharacter.assert_not_called()


def test_remove_character_info_passes_explicit_unique_rows_to_model():
    controller, models, panel, _nav, _dialogs = make_controller()
    panel.characters.currentCharacterID.return_value = "alice"
    rows = []
    for row in (2, 2, 0):
        index = MagicMock()
        index.row.return_value = row
        rows.append(index)
    panel.info.selectedIndexes.return_value = rows

    controller.remove_character_info()

    models.characters.removeCharacterInfo.assert_called_once_with(
        "alice", {0, 2}
    )


def test_selection_is_recorded_as_one_statement():
    """Pushing the entry and saying whether the selection was empty were
    always used together -- the second decides whether the first replaces
    the last entry or follows it.
    """
    controller, _models, panel, navigation, _dialogs = make_controller()
    alice = MagicMock()
    alice.ID.return_value = "alice"
    panel.characters.currentCharacters.return_value = [alice]

    controller.record_current_selection()

    navigation.record.assert_called_once_with(
        ("character", "alice"),
        selection_empty=False,
    )

    panel.characters.currentCharacters.return_value = []
    navigation.record.reset_mock()

    controller.record_current_selection()

    navigation.record.assert_called_once_with(
        ("character", None),
        selection_empty=True,
    )


def test_information_is_asked_for_through_the_dialog_service():
    controller, models, panel, _nav, dialogs = make_controller()
    panel.characters.currentCharacterID.return_value = "alice"
    dialogs.ask_name_and_value.return_value = ("Eyes", "Green")

    controller.add_character_info()

    models.characters.addCharacterInfo.assert_called_once_with(
        "alice", "Eyes", "Green",
    )

    models.characters.addCharacterInfo.reset_mock()
    dialogs.ask_name_and_value.return_value = None

    controller.add_character_info()

    models.characters.addCharacterInfo.assert_not_called()
