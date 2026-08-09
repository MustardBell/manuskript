"""Semantic tab and selection history for one workspace."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Tuple


@dataclass(frozen=True)
class WorkspaceSelectionTabs:
    characters: int
    plots: int
    world: int
    outline: int
    editor: int


@dataclass(frozen=True)
class WorkspaceSelectionViews:
    """Stable controls needed to interpret workspace selection changes."""

    tabs: Any
    organize_action: Any
    editor_actions: Tuple[Any, ...]
    outline_tree: Any
    project_tree: Any
    positions: WorkspaceSelectionTabs

    @classmethod
    def for_window(cls, window):
        return cls(
            tabs=window.tabMain,
            organize_action=window.menuOrganize.menuAction(),
            editor_actions=(
                window.actCut,
                window.actCopy,
                window.actPaste,
                window.actDelete,
                window.actRename,
            ),
            outline_tree=window.treeOutlineOutline,
            project_tree=window.corePanels.project_tree.tree,
            positions=WorkspaceSelectionTabs(
                characters=window.TabPersos,
                plots=window.TabPlots,
                world=window.TabWorld,
                outline=window.TabOutline,
                editor=window.TabRedac,
            ),
        )


class WorkspaceSelectionHistory:
    """Apply one transient-selection policy to every workspace panel."""

    def __init__(self, navigation):
        self._navigation = navigation
        self._replace_next = True

    def record_selection(self, entry, selection_empty):
        self._record(entry)
        self._replace_next = selection_empty

    def record_location(self, entry, *, replace_next=False):
        self._record(entry)
        self._replace_next = replace_next

    def reset(self):
        self._replace_next = True
        self._navigation.reset()

    def _record(self, entry):
        self._navigation.record(entry, replace=self._replace_next)

    def dispose(self):
        self._navigation = None


class WorkspaceSelectionController:
    """Turn UI location changes into typed navigation-history entries.

    Selection models can briefly become empty while moving between items.
    That empty entry is transient: the next stable selection replaces it.
    The policy used to live in a mutable ``MainWindow`` flag shared by tab
    and tree callbacks.  Keeping it with the history events makes its state
    transition explicit and independently testable.
    """

    def __init__(
            self,
            views,
            runtime,
            history,
            tab_recorders: Mapping[int, Callable[[], None]],
    ):
        self._views = views
        self._runtime = runtime
        self._history = history
        self._tab_recorders = dict(tab_recorders)

    def tab_changed(self, _index=None):
        views = self._views
        tab_index = views.tabs.currentIndex()
        editor_active = tab_index == views.positions.editor
        views.organize_action.setEnabled(editor_active)
        for action in views.editor_actions:
            action.setEnabled(editor_active)

        recorder = self._tab_recorders.get(tab_index)
        if recorder is not None:
            recorder()
            return
        if tab_index == views.positions.outline:
            self._record_tab_selection("outline", views.outline_tree)
        elif tab_index == views.positions.editor:
            self._record_tab_selection("redac", views.project_tree)
        else:
            self._history.record_location(("main", tab_index))

    def outline_selection_changed(self, *_args):
        self._record_selection("outline", self._views.outline_tree)

    def project_selection_changed(self, *_args):
        self._record_selection("redac", self._views.project_tree)

    def _record_tab_selection(self, kind, tree):
        valid, item_id = self._current_outline_selection(tree)
        # A selection signal for the item already displayed by the newly
        # active tab describes the same location, so it replaces this entry.
        self._history.record_location(
            (kind, item_id),
            replace_next=valid,
        )

    def _record_selection(self, kind, tree):
        valid, item_id = self._current_outline_selection(tree)
        # Clearing is often an intermediate selection-model event.  If a
        # stable item follows, replace the empty entry rather than exposing
        # it as an extra Back/Forward stop.
        self._history.record_selection(
            (kind, item_id),
            selection_empty=not valid,
        )

    def _current_outline_selection(self, tree):
        index = tree.selectionModel().currentIndex()
        if not index.isValid():
            return False, None
        return True, self._runtime.models.outline.ID(index)

    def dispose(self):
        self._views = None
        self._runtime = None
        self._history = None
        self._tab_recorders.clear()
