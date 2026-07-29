from dataclasses import dataclass
from typing import Callable

from manuskript.commands import DocumentCommand
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationState,
)


@dataclass(frozen=True)
class TextEditorContext:
    """Application actions available to project-bound text editors."""

    settings: object
    reload_fonts: Callable
    create_character: Callable[[str], None]
    create_plot: Callable[[str], None]
    create_world_item: Callable[[str], None]
    invoke_outline_command: Callable[[DocumentCommand], None]
    markdown_presentation: MarkdownPresentationState


def text_editor_context_for(window, settings):
    """Adapt the main UI to the text editor action boundary."""
    markdown_presentation = MarkdownPresentationState(settings)

    def reload_fonts():
        from manuskript.ui.views.textEditView import textEditView

        for editor in window.findChildren(textEditView):
            editor.loadFontSettings()

    def create_character(name):
        window.tabMain.setCurrentIndex(window.TabPersos)
        character = window.mdlCharacter.addCharacter(name=name)
        item = window.lstCharacters.getItemByID(character.ID())
        window.lstCharacters.setCurrentItem(item)

    def create_plot(name):
        window.tabMain.setCurrentIndex(window.TabPlots)
        window.mdlPlots.addPlot(name)

    def create_world_item(name):
        window.tabMain.setCurrentIndex(window.TabWorld)
        window.worldController.add_item(title=name)

    def invoke_outline_command(command):
        command = DocumentCommand(command)
        handler = getattr(window.treeRedacOutline, command.value, None)
        if callable(handler):
            handler()

    return TextEditorContext(
        settings=settings,
        reload_fonts=reload_fonts,
        create_character=create_character,
        create_plot=create_plot,
        create_world_item=create_world_item,
        invoke_outline_command=invoke_outline_command,
        markdown_presentation=markdown_presentation,
    )
