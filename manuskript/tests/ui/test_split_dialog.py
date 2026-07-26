from unittest.mock import MagicMock

from manuskript.ui.tools.splitDialog import (
    decode_split_mark,
    item_for_index,
    open_split_dialog,
    split_items,
)


def test_item_for_index_uses_project_root_for_invalid_index():
    index = MagicMock()
    root_item = object()
    index.isValid.return_value = False

    assert item_for_index(index, root_item) is root_item


def test_split_items_resolves_valid_and_root_indexes():
    valid_index = MagicMock()
    invalid_index = MagicMock()
    item = MagicMock()
    root_item = MagicMock()
    valid_index.isValid.return_value = True
    valid_index.internalPointer.return_value = item
    invalid_index.isValid.return_value = False

    split_items([valid_index, invalid_index], root_item, "\n---\n")

    item.split.assert_called_once_with("\n---\n")
    root_item.split.assert_called_once_with("\n---\n")


def test_decode_split_mark_expands_supported_escapes():
    assert decode_split_mark("one\\ntwo\\tthree") == "one\ntwo\tthree"


def test_open_split_dialog_applies_accepted_mark():
    item = MagicMock()
    index = MagicMock()
    index.isValid.return_value = True
    index.internalPointer.return_value = item

    class AcceptedDialog:
        def __init__(self, parent, indexes, root_item, mark):
            pass

        def exec(self):
            return True

        def textValue(self):
            return "\\n---\\n"

    accepted = open_split_dialog(
        None,
        [index],
        MagicMock(),
        dialog_type=AcceptedDialog,
    )

    assert accepted is True
    item.split.assert_called_once_with("\n---\n")
