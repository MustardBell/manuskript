"""The views one project is shown through, named rather than looked up.

Binding a project used to take a window and fish everything out of it:
models, trees, the editor, the metadata panel, the cheat sheet, search,
plugin state. A window that answers any question is a service locator,
and with one window the questions had obvious answers -- there was only
one outline tree, one editor, one metadata panel.

A second window makes every one of those questions real: which tree,
which editor, whose selection. This says which, once, in one place. The
binding receives a view set and never sees a window, so the answers are
given by whoever built the set rather than found by whoever needed one.

:meth:`ProjectViewSet.for_window` is the only code that reaches into a
window for these, and it is the whole of that coupling.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple


@dataclass(frozen=True)
class ProjectViewSet:
    """One window's worth of views onto a project.

    The models and the project services are the project's and are the
    same in every set; everything else is this window's own.
    """

    #: The project's models, as :class:`ProjectModels`.
    models: Any

    # ------------------------------------------------ project services
    settings: Any = None
    card_styles: Any = None
    undo_stack: Any = None
    show_status: Optional[Callable[..., None]] = None
    #: Called for the page-type service, which arrives with plugins and
    #: may not be there at all.
    page_types: Optional[Callable[[], Any]] = None

    # --------------------------------------------------- this window's
    #: Trees that show the outline and take a project model.
    outline_trees: Tuple[Any, ...] = ()
    #: Where documents are edited -- the tab and split area.
    document_area: Any = None
    metadata_panel: Any = None
    item_editor: Any = None
    storyline: Any = None
    cheat_sheet: Any = None
    search_view: Any = None
    #: The signal that says this window's selection changed.
    selection_changed: Any = None
    open_index: Optional[Callable[..., Any]] = None
    open_indexes: Optional[Callable[..., Any]] = None

    # ------------------------------------------------- window adapters
    #: Every model-backed text editor in this window, asked for freshly
    #: because panels come and go.
    text_editors: Optional[Callable[[], Any]] = None
    #: Every completing editor in this window, likewise.
    completers: Optional[Callable[[], Any]] = None
    #: How this window navigates to a reference.
    navigation: Any = None
    #: Builds this window's text editor context.
    text_editor_context: Optional[Callable[[], Any]] = None
    #: Builds this window's search result views, given the reference
    #: service, which only exists once binding has started.
    result_views: Optional[Callable[[Any], Any]] = None

    @classmethod
    def for_window(cls, window):
        """One window's views, read off it once.

        The only place that reaches into a window for any of this. Every
        attribute here is a coupling to be removed later by moving the
        view somewhere that can be asked for it directly; while they
        remain, they are at least all in view.
        """
        from manuskript.ui.reference_navigation import (
            reference_navigation_for,
        )
        from manuskript.ui.search_context import SearchResultViewAdapter
        from manuskript.ui.views.MDEditCompleter import MDEditCompleter
        from manuskript.ui.views.textEditView import textEditView
        from manuskript.ui.views.text_editor_context import (
            text_editor_context_for,
        )

        runtime = window.projectRuntime
        return cls(
            models=runtime.models,
            settings=runtime.settingsManager,
            card_styles=getattr(window, "cardStyles", None),
            undo_stack=runtime.undoStack,
            show_status=window.statusPresenter.show,
            page_types=lambda: (
                window.pluginUi.pageTypes
                if window.pluginUi is not None
                else None
            ),
            outline_trees=(
                window.treeRedacOutline,
                window.treeOutlineOutline,
            ),
            document_area=window.mainEditor,
            metadata_panel=window.redacMetadata,
            item_editor=window.outlineItemEditor,
            storyline=window.storylineView,
            cheat_sheet=window.cheatSheet,
            search_view=window.widget,
            selection_changed=window.redacMetadata.selectionChanged,
            open_index=window.openIndex,
            open_indexes=window.openIndexes,
            text_editors=lambda: window.findChildren(textEditView),
            completers=lambda: window.findChildren(MDEditCompleter),
            navigation=reference_navigation_for(
                window,
                runtime.models,
            ),
            text_editor_context=lambda: text_editor_context_for(
                window,
                runtime.settingsManager,
                runtime.models,
                # The project's, so both windows type into one text.
                runtime.documentBuffers,
            ),
            result_views=lambda references: SearchResultViewAdapter(
                window,
                references,
            ),
        )
