from unittest.mock import MagicMock

from manuskript.commands import DocumentCommand
from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.views.text_editor_context import text_editor_context_for


def make_window():
    window = MagicMock()
    window.TabPersos = 2
    window.TabPlots = 3
    window.TabWorld = 4
    return window


def test_text_editor_context_refreshes_all_current_editors():
    window = make_window()
    first = MagicMock()
    second = MagicMock()
    window.findChildren.return_value = [first, second]
    context = text_editor_context_for(window, MagicMock())

    context.reload_fonts()

    first.loadFontSettings.assert_called_once_with()
    second.loadFontSettings.assert_called_once_with()


def test_text_editor_context_creates_and_selects_character():
    window = make_window()
    settings = MagicMock()
    character = MagicMock()
    character.ID.return_value = "alice"
    window.mdlCharacter.addCharacter.return_value = character
    item = MagicMock()
    window.lstCharacters.getItemByID.return_value = item
    context = text_editor_context_for(window, settings)

    context.create_character("Alice")

    window.tabMain.setCurrentIndex.assert_called_once_with(window.TabPersos)
    window.mdlCharacter.addCharacter.assert_called_once_with(name="Alice")
    window.lstCharacters.getItemByID.assert_called_once_with("alice")
    window.lstCharacters.setCurrentItem.assert_called_once_with(item)
    assert context.settings is settings


def test_text_editor_context_creates_plot_and_world_item():
    window = make_window()
    context = text_editor_context_for(window, MagicMock())

    context.create_plot("Quest")
    context.create_world_item("City")

    assert window.tabMain.setCurrentIndex.call_args_list[0].args == (
        window.TabPlots,
    )
    assert window.tabMain.setCurrentIndex.call_args_list[1].args == (
        window.TabWorld,
    )
    window.mdlPlots.addPlot.assert_called_once_with("Quest")
    window.worldController.add_item.assert_called_once_with(title="City")


def test_text_editor_context_routes_typed_outline_command():
    window = make_window()
    context = text_editor_context_for(window, MagicMock())

    context.invoke_outline_command(DocumentCommand.MOVE_DOWN)

    window.treeRedacOutline.moveDown.assert_called_once_with()


def test_text_editor_routes_rename_as_typed_command():
    context = MagicMock()
    context.settings = MagicMock()
    editor = textEditView(spellcheck=False)
    editor.set_text_editor_context(context)
    editor._index = MagicMock()

    editor.rename()

    context.invoke_outline_command.assert_called_once_with(
        DocumentCommand.RENAME
    )
