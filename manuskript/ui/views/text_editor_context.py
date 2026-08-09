from dataclasses import dataclass
from typing import Callable, Optional

from manuskript.commands import DocumentCommand
@dataclass(frozen=True)
class TextEditorContext:
    """Application actions available to project-bound text editors."""

    settings: object
    reload_fonts: Callable
    create_character: Callable[[str], None]
    create_plot: Callable[[str], None]
    create_world_item: Callable[[str], None]
    invoke_outline_command: Callable[[DocumentCommand], None]
    markup_profiles: Optional[object] = None
    page_types: Optional[object] = None
    #: The project's text buffers, so two views of one document are two
    #: viewports on one text rather than two copies of it.
    document_buffers: Optional[object] = None
    #: Report a real editor focus event to its workspace. QApplication's
    #: global focusChanged signal is not delivered consistently by every Qt
    #: platform plugin, especially for viewport clicks in headless sessions.
    focus_received: Optional[Callable[[object], None]] = None
    #: Release a disappearing editor before its native widget is destroyed.
    focus_released: Optional[Callable[[object], None]] = None


def text_editor_context_for(window, settings, models, buffers=None):
    """Adapt the main UI to the text editor action boundary.

    Takes the project's models rather than reading them off the window.
    The window is here because this adapts one -- switching tabs, finding
    widgets -- but the models belong to the project, and reaching through
    a window for them is what let a window answer any question at all.
    """
    def reload_fonts():
        from manuskript.ui.views.textEditView import textEditView

        for editor in window.findChildren(textEditView):
            editor.loadFontSettings()

    def create_character(name):
        window.tabMain.setCurrentIndex(window.TabPersos)
        character = models.characters.addCharacter(name=name)
        item = window.lstCharacters.getItemByID(character.ID())
        window.lstCharacters.setCurrentItem(item)

    def create_plot(name):
        window.tabMain.setCurrentIndex(window.TabPlots)
        models.plots.addPlot(name)

    def create_world_item(name):
        window.tabMain.setCurrentIndex(window.TabWorld)
        window.worldController.add_item(title=name)

    def invoke_outline_command(command):
        command = DocumentCommand(command)
        handler = getattr(
            window.corePanels.project_tree.tree,
            command.value,
            None,
        )
        if callable(handler):
            handler()

    def focus_received(editor):
        # This context already names the owning workspace, so do not ask Qt
        # to rediscover it through QWidget.window(). Platform plugins can
        # report a transient native top-level while a window is being shown.
        # The later application-global delivery is coalesced by the focus
        # controller.
        window.windowRegistry.activate(window)
        window.workspaceFocus.focus_changed(None, editor)

    def focus_released(editor):
        focus = window.workspaceFocus
        if (
            focus.focused_widget is editor
            or focus.markup_target is editor
        ):
            focus.focus_changed(editor, None)

    return TextEditorContext(
        settings=settings,
        document_buffers=buffers,
        focus_received=focus_received,
        focus_released=focus_released,
        reload_fonts=reload_fonts,
        create_character=create_character,
        create_plot=create_plot,
        create_world_item=create_world_item,
        invoke_outline_command=invoke_outline_command,
        markup_profiles=(
            window.pluginUi.markupProfiles
            if window.pluginUi is not None
            else None
        ),
        page_types=(
            window.pluginUi.pageTypes
            if window.pluginUi is not None
            else None
        ),
    )
