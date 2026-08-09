from unittest.mock import MagicMock

from PyQt5.QtGui import QColor

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
    context = text_editor_context_for(
        window, MagicMock(), MagicMock(),
    )

    context.reload_fonts()

    first.loadFontSettings.assert_called_once_with()
    second.loadFontSettings.assert_called_once_with()


def test_text_editor_context_creates_and_selects_character():
    window = make_window()
    settings = MagicMock()
    character = MagicMock()
    character.ID.return_value = "alice"
    models = MagicMock()
    models.characters.addCharacter.return_value = character
    item = MagicMock()
    window.lstCharacters.getItemByID.return_value = item
    context = text_editor_context_for(window, settings, models)

    context.create_character("Alice")

    window.tabMain.setCurrentIndex.assert_called_once_with(window.TabPersos)
    models.characters.addCharacter.assert_called_once_with(name="Alice")
    window.lstCharacters.getItemByID.assert_called_once_with("alice")
    window.lstCharacters.setCurrentItem.assert_called_once_with(item)
    assert context.settings is settings


def test_text_editor_context_creates_plot_and_world_item():
    window = make_window()
    models = MagicMock()
    context = text_editor_context_for(window, MagicMock(), models)

    context.create_plot("Quest")
    context.create_world_item("City")

    assert window.tabMain.setCurrentIndex.call_args_list[0].args == (
        window.TabPlots,
    )
    assert window.tabMain.setCurrentIndex.call_args_list[1].args == (
        window.TabWorld,
    )
    models.plots.addPlot.assert_called_once_with("Quest")
    window.worldController.add_item.assert_called_once_with(title="City")


def test_text_editor_context_routes_typed_outline_command():
    window = make_window()
    context = text_editor_context_for(
        window, MagicMock(), MagicMock(),
    )

    context.invoke_outline_command(DocumentCommand.MOVE_DOWN)

    window.corePanels.project_tree.tree.moveDown.assert_called_once_with()


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


def test_unattached_text_editors_use_isolated_local_settings():
    first = textEditView(spellcheck=False)
    second = textEditView(spellcheck=False)
    context = MagicMock()
    context.settings = MagicMock()

    assert first.settings is not second.settings

    first.set_text_editor_context(context)

    assert first.settings is context.settings
    assert second.settings is not context.settings


def test_highlighter_reads_settings_owned_by_its_editor():
    editor = textEditView(spellcheck=False, highlighting=True)
    editor.settings.textEditor["fontColor"] = "#123456"
    editor.settings.textEditor["background"] = "#ffffff"

    editor.highlighter.updateColorScheme(rehighlight=False)

    assert editor.highlighter.defaultTextColor == QColor("#123456")
