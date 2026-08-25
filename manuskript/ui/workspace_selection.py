"""Semantic surface and selection history for one workspace."""

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Tuple

from manuskript.panels.core import EDITOR, OUTLINE


@dataclass(frozen=True)
class WorkspaceSelectionViews:
    """Stable controls needed to interpret workspace selection changes."""

    organize_action: Any
    editor_actions: Tuple[Any, ...]
    resolve_surface: Callable[[Any], str]
    surface_focused: Callable[[str], None]
    surface_widget: Callable[[str], Any]
    outline_selection: Any

    @classmethod
    def for_window(cls, window):
        def resolve_surface(widget):
            """Which of this window's panels or surfaces holds this widget.

            Both owners, walking up from wherever the focus landed. A
            window that asked only the panel host would answer "" for
            every click inside the editor, the outline or the cast --
            which is to say for almost every click a writer makes.
            """
            candidate = widget
            while candidate is not None:
                for host in (window.panelHost, window.surfaceHost):
                    for panel_id, instance in host.instances.items():
                        if candidate in (instance.widget, instance.container):
                            return panel_id
                candidate = candidate.parent()
            return ""

        def surface_widget(surface_id):
            instance = window.surfaceHost.instance(surface_id)
            return instance.widget if instance is not None else None

        return cls(
            organize_action=window.menuOrganize.menuAction(),
            editor_actions=(
                window.actCut,
                window.actCopy,
                window.actPaste,
                window.actDelete,
                window.actRename,
            ),
            resolve_surface=resolve_surface,
            surface_focused=window.notePanelFocus,
            surface_widget=surface_widget,
            outline_selection=window.outlineSelection,
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
    """Turn panel locations and outline selections into history entries."""

    def __init__(
        self,
        views,
        runtime,
        history,
        surface_recorders: Mapping[str, Any],
    ):
        self._views = views
        self._runtime = runtime
        self._history = history
        self._surface_recorders = dict(surface_recorders)
        self._active_surface = ""

    @property
    def active_surface(self):
        return self._active_surface

    def surface_changed(self, panel_id):
        """Record the semantic surface selected through Navigation."""
        self._active_surface = str(panel_id or "")
        self._set_editor_actions(self._active_surface == EDITOR)
        recorder = self._surface_recorders.get(self._active_surface)
        if recorder is not None:
            recorder()
        elif self._active_surface == OUTLINE:
            panel = self._views.surface_widget(OUTLINE)
            if panel is not None:
                self._record_surface_selection(
                    "outline", panel.treeOutlineOutline,
                )
        elif self._active_surface == EDITOR:
            self._record_surface_selection(
                "redac", self._views.outline_selection,
            )
        elif self._active_surface:
            self._history.record_location(("panel", self._active_surface))

    def focus_changed(self, _old, new):
        """Make direct panel focus a semantic location, not visibility."""
        panel_id = self._views.resolve_surface(new)
        if panel_id and panel_id != self._active_surface:
            self._views.surface_focused(panel_id)
            self.surface_changed(panel_id)
            return
        self._set_editor_actions(panel_id == EDITOR)

    def _set_editor_actions(self, enabled):
        self._views.organize_action.setEnabled(enabled)
        for action in self._views.editor_actions:
            action.setEnabled(enabled)

    def outline_selection_changed(self, *_args):
        panel = self._views.surface_widget(OUTLINE)
        if panel is not None:
            self._record_selection("outline", panel.treeOutlineOutline)

    def project_selection_changed(self, *_args):
        self._record_selection("redac", self._views.outline_selection)

    def _record_surface_selection(self, kind, tree):
        valid, item_id = self._current_outline_selection(tree)
        self._history.record_location(
            (kind, item_id),
            replace_next=valid,
        )

    def _record_selection(self, kind, tree):
        valid, item_id = self._current_outline_selection(tree)
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
        self._surface_recorders.clear()
