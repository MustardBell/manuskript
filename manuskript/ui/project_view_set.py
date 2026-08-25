"""The views one project is shown through, grouped by what binds them.

Binding a project used to take a window and fish everything out of it:
models, trees, the editor, the metadata panel, the cheat sheet, search,
plugin state. A window that answers any question is a service locator,
and with one window the questions had obvious answers -- there was only
one outline tree, one editor, one metadata panel.

A second window makes every one of those questions real: which tree,
which editor, whose selection. This says which, once, in one place.

Grouped rather than flat, and that is the second thing this fixes. As one
list of twenty-one fields it was a catalog: every binding could see every
view, so nothing stopped the search binding reaching for the metadata
panel, and the pressure on the file was to grow one more field per
feature forever. Each group below is what one binding is handed. A
binding that has never heard of the corkboard cannot come to depend on
it.

:meth:`ProjectViewSet.for_window` is the only code that reaches into a
window for any of this, and it is the whole of that coupling.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from manuskript.panels.core import EDITOR


@dataclass(frozen=True)
class EditorViews:
    """Where documents are edited, and what editing them needs.

    The trees, the tab-and-split area and every model-backed text editor,
    plus the project services the outline views are built from. Nothing
    about metadata, references or search.
    """

    #: The project tree is a tool panel and remains in this workspace.
    project_tree: Any
    #: Builds this window's text editor context.
    text_editor_context: Optional[Callable[[], Any]]
    open_index: Optional[Callable[..., Any]]
    open_indexes: Optional[Callable[..., Any]]
    #: The signal that says this window's selection changed.
    selection_changed: Any
    show_status: Optional[Callable[..., None]]
    settings: Any
    card_styles: Any
    undo_stack: Any


@dataclass(frozen=True)
class MetadataViews:
    """The views that show one outline item's own facts."""

    panel: Any
    #: Called for the page-type service, which arrives with plugins and
    #: may not be there at all.
    page_types: Optional[Callable[[], Any]]


@dataclass(frozen=True)
class ReferencePanelViews:
    """The views that show how the project's items refer to each other.

    The storyline, the cheat sheet, and the editors that complete a
    reference as it is typed. All three read through the one reference
    service, which is why they are bound together.
    """

    storyline: Any
    cheat_sheet: Any


@dataclass(frozen=True)
class SearchViews:
    """Where the project is searched, and where results are shown."""

    view: Any
    #: Builds this window's search result views, given the reference
    #: service, which only exists once binding has started.
    result_views: Optional[Callable[[Any], Any]]


@dataclass(frozen=True)
class ProjectViewSet:
    """One window's views onto a project, in the groups that bind them.

    The models are the project's and are the same in every set; the groups
    are this window's own. ``navigation`` is here rather than in a group
    because the reference service is made from it, and that service is
    shared by two of the groups rather than belonging to either.
    """

    #: The project's models, as :class:`ProjectModels`.
    models: Any
    #: How this window navigates to a reference.
    navigation: Any
    editors: EditorViews
    metadata: MetadataViews
    reference_panels: ReferencePanelViews
    search: SearchViews

    @classmethod
    def for_window(cls, window):
        """One window's stable views and living-surface providers.

        The only place that reaches into a window for any of this. Every
        attribute here is a coupling to be removed later by moving the
        view somewhere that can be asked for it directly; while they
        remain, they are at least all in view.
        """
        from manuskript.ui.reference_navigation import (
            reference_navigation_for,
        )
        from manuskript.ui.search_context import (
            SearchResultViewAdapter,
            SearchResultViews,
        )
        from manuskript.ui.views.text_editor_context import (
            text_editor_context_for,
        )

        runtime = window.projectRuntime
        core = window.corePanels
        project_tree = core.optional_tool("project_tree")
        project_tree = project_tree.tree if project_tree is not None else None
        metadata = core.optional_tool("metadata")
        storyline = core.optional_tool("storyline")
        search_result_views = SearchResultViews.for_window(window)
        navigation = reference_navigation_for(
            window,
            runtime.models,
            window.entityWorkspace.open,
        )

        def open_indexes(indexes):
            instance = window.surfaceHost.instance(EDITOR)
            if instance is not None:
                return instance.widget.editor.openIndexes(
                    indexes, newTab=True,
                )
            return None

        return cls(
            models=runtime.models,
            navigation=navigation,
            editors=EditorViews(
                project_tree=project_tree,
                text_editor_context=lambda: text_editor_context_for(
                    window,
                    runtime.settingsManager,
                    runtime.models,
                    # The project's, so both windows type into one text.
                    runtime.documentBuffers,
                    runtime.projectManager.storage.reference_index,
                    runtime.projectManager.storage.entity_catalog,
                    runtime.projectManager.createEntity,
                    navigation.open_entity,
                    lambda: runtime.projectManager.storage.persistence_strategy,
                ),
                open_index=(
                    project_tree.setCurrentIndex
                    if project_tree is not None else None
                ),
                open_indexes=open_indexes,
                selection_changed=(
                    metadata.selectionChanged
                    if metadata is not None else None
                ),
                show_status=window.statusPresenter.show,
                settings=runtime.settingsManager,
                card_styles=getattr(window, "cardStyles", None),
                undo_stack=runtime.undoStack,
            ),
            metadata=MetadataViews(
                panel=metadata,
                page_types=lambda: (
                    window.pluginUi.pageTypes
                    if window.pluginUi is not None
                    else None
                ),
            ),
            reference_panels=ReferencePanelViews(
                storyline=storyline,
                cheat_sheet=window.cheatSheet,
            ),
            search=SearchViews(
                view=window.widget,
                result_views=lambda references: SearchResultViewAdapter(
                    search_result_views,
                    references,
                ),
            ),
        )
