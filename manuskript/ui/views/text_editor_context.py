from dataclasses import dataclass
from typing import Callable, Optional

from manuskript.commands import DocumentCommand
from manuskript.domain.story_assertions import TemporalPoint


@dataclass(frozen=True)
class TextEditorContext:
    """Application actions available to project-bound text editors."""

    settings: object
    reload_fonts: Callable
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
    #: Generic Format 2 wikilink operations. The editor sees commands, not
    #: the project storage or a window.
    complete_wikilink: Optional[Callable[[str], tuple]] = None
    open_wikilink: Optional[Callable[[str], bool]] = None
    entity_reference_choices: Optional[Callable[[str], tuple]] = None
    entity_schemas: Optional[Callable[[], tuple]] = None
    create_entity: Optional[Callable[[str, str], object]] = None
    can_write_assertions: Optional[Callable[[], bool]] = None
    temporal_reference_choices: Optional[Callable[[], tuple]] = None
    can_write_timeline: Optional[Callable[[], bool]] = None


def text_editor_context_for(
    window,
    settings,
    models,
    buffers=None,
    reference_index=None,
    open_document=None,
    entity_catalog=None,
    create_native_entity=None,
    open_entity=None,
    persistence_strategy=None,
):
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

    def complete_wikilink(prefix):
        return (
            reference_index.complete(prefix)
            if reference_index is not None
            else ()
        )

    def open_wikilink(target):
        if reference_index is None:
            return False
        _resolution, document = reference_index.resolve(target)
        if document is None:
            return False
        if open_document is not None and open_document(document.id):
            return True
        return bool(open_entity is not None and open_entity(document.id))

    def entity_reference_choices(surface):
        if entity_catalog is None or not entity_catalog.writable:
            return ()
        return entity_catalog.reference_choices(surface)

    def entity_schemas():
        if entity_catalog is None or not entity_catalog.writable:
            return ()
        return entity_catalog.schemas.schemas

    def create_entity(entity_type, title):
        if create_native_entity is None or entity_catalog is None:
            return None
        entity = create_native_entity(entity_type, title)
        if open_entity is not None:
            open_entity(entity.id)
        return entity_catalog.reference_choice(entity, exact_match=True)

    def can_write_assertions():
        strategy = (
            persistence_strategy()
            if callable(persistence_strategy)
            else persistence_strategy
        )
        return bool(
            strategy is not None
            and strategy.supports("assertions.write", write=True)
        )

    def can_write_timeline():
        strategy = (
            persistence_strategy()
            if callable(persistence_strategy)
            else persistence_strategy
        )
        return bool(
            strategy is not None
            and strategy.supports("timeline.write", write=True)
        )

    def temporal_reference_choices():
        if reference_index is None:
            return ()
        entities = {
            entity.id: entity
            for entity in (
                entity_catalog.entities if entity_catalog is not None else ()
            )
        }
        choices = []
        for document in reference_index.documents:
            if document.id in entities:
                if entities[document.id].type == "event":
                    choices.append((
                        "{} — event".format(document.title),
                        TemporalPoint.story_reference("entity", document.id),
                    ))
                continue
            choices.extend((
                (
                    "{} — narrative order".format(document.title),
                    TemporalPoint.narrative("document", document.id),
                ),
                (
                    "{} — story chronology".format(document.title),
                    TemporalPoint.story_reference("document", document.id),
                ),
            ))
        return tuple(choices)

    return TextEditorContext(
        settings=settings,
        document_buffers=buffers,
        focus_received=focus_received,
        focus_released=focus_released,
        complete_wikilink=complete_wikilink,
        open_wikilink=open_wikilink,
        entity_reference_choices=entity_reference_choices,
        entity_schemas=entity_schemas,
        create_entity=create_entity,
        can_write_assertions=can_write_assertions,
        temporal_reference_choices=temporal_reference_choices,
        can_write_timeline=can_write_timeline,
        reload_fonts=reload_fonts,
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
