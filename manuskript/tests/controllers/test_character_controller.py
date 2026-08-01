from unittest.mock import MagicMock, call, patch

from PyQt5.QtWidgets import QMessageBox

from manuskript.controllers.character_controller import CharacterController


def make_controller():
    window = MagicMock()
    window.tr.side_effect = lambda text: text
    return CharacterController(window), window


def test_character_selection_text_handles_multiple_and_empty_selections():
    controller, window = make_controller()
    alice = MagicMock()
    alice.name.return_value = "Alice"
    bob = MagicMock()
    bob.name.return_value = "Bob"
    window.lstCharacters.currentCharacters.return_value = [alice, bob]

    assert controller.character_selection_text() == '"Alice", "Bob"'

    window.lstCharacters.currentCharacters.return_value = []
    assert controller.character_selection_text() == ""


def test_delete_characters_removes_each_character_and_clears_pov_references():
    controller, window = make_controller()
    window.lstCharacters.currentCharacterIDs.return_value = ["alice", "bob"]
    window.mdlOutline.findItemsByPOV.side_effect = [
        ["alice-scene"],
        ["bob-scene"],
    ]
    alice_scene = MagicMock()
    bob_scene = MagicMock()
    window.mdlOutline.getItemByID.side_effect = {
        "alice-scene": alice_scene,
        "bob-scene": bob_scene,
    }.get

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.Yes
    ):
        deleted = controller.delete_characters()

    assert deleted == ["alice", "bob"]
    assert window.mdlCharacter.removeCharacter.call_args_list == [
        call("alice"),
        call("bob"),
    ]
    alice_scene.resetPOV.assert_called_once_with()
    bob_scene.resetPOV.assert_called_once_with()


def test_delete_characters_respects_cancel():
    controller, window = make_controller()
    window.lstCharacters.currentCharacterIDs.return_value = ["alice"]

    with patch.object(
        QMessageBox, "warning", return_value=QMessageBox.No
    ):
        deleted = controller.delete_characters()

    assert deleted == []
    window.mdlCharacter.removeCharacter.assert_not_called()


def test_remove_character_info_passes_explicit_unique_rows_to_model():
    controller, window = make_controller()
    window.lstCharacters.currentCharacterID.return_value = "alice"
    first = MagicMock()
    first.row.return_value = 2
    duplicate = MagicMock()
    duplicate.row.return_value = 2
    second = MagicMock()
    second.row.return_value = 0
    window.tblPersoInfos.selectedIndexes.return_value = [
        first,
        duplicate,
        second,
    ]

    controller.remove_character_info()

    window.mdlCharacter.removeCharacterInfo.assert_called_once_with(
        "alice", {0, 2}
    )
