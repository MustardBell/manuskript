"""Focused command targets owned by one workspace window."""

from dataclasses import dataclass
from typing import Any, Tuple
from weakref import WeakMethod, ref

from manuskript.ui.views.MDEditView import MDEditView


@dataclass(frozen=True)
class WorkspaceFocusViews:
    """Stable roots whose descendants accept document commands."""

    document_targets: Tuple[Any, ...]

    @classmethod
    def for_window(cls, window):
        return cls(
            document_targets=(
                window.corePanels.project_tree.tree,
                window.mainEditor,
            )
        )


class WorkspaceFocusController:
    """Resolve focus into the command endpoints for one workspace.

    Application focus is global, but command targets are not.  The window
    registry selects the workspace that gained focus and calls this controller;
    document and markup routers then ask it for their current endpoint.
    """

    def __init__(self, views):
        self._views = views
        self._document_target = None
        self._markup_target = None
        self._focused_widget = None
        self._listeners = []

    @property
    def document_target(self):
        return self._document_target

    @property
    def markup_target(self):
        return self._markup_target

    def current_document_target(self):
        """Return the endpoint used by document command routing."""
        return self._document_target

    def current_markup_target(self):
        """Return the endpoint used by markup command routing."""
        return self._markup_target

    @property
    def focused_widget(self):
        return self._focused_widget

    def subscribe(self, listener):
        """Observe this workspace's focus without retaining the receiver."""
        if any(item() == listener for item in self._listeners):
            return
        try:
            listener_ref = WeakMethod(listener)
        except TypeError:
            listener_ref = ref(listener)
        self._listeners.append(listener_ref)

    def unsubscribe(self, listener):
        remaining = []
        for listener_ref in self._listeners:
            callback = listener_ref()
            if callback is not None and callback != listener:
                remaining.append(listener_ref)
        self._listeners = remaining

    def focus_changed(self, _old, new):
        self._focused_widget = new
        self._markup_target = self._find_markdown_editor(new)

        candidate = new
        while candidate is not None:
            if candidate in self._views.document_targets:
                self._document_target = candidate
                break
            candidate = candidate.parent()

        listeners = []
        callbacks = []
        for listener_ref in self._listeners:
            listener = listener_ref()
            if listener is not None:
                listeners.append(listener_ref)
                callbacks.append(listener)
        self._listeners = listeners
        for listener in callbacks:
            listener(_old, new)

    @staticmethod
    def _find_markdown_editor(widget):
        candidate = widget
        while candidate is not None:
            if isinstance(candidate, MDEditView):
                return candidate
            canonical_editor = getattr(candidate, "canonicalEditor", None)
            if isinstance(canonical_editor, MDEditView):
                return canonical_editor
            candidate = candidate.parent()
        return None

    def dispose(self):
        self._document_target = None
        self._markup_target = None
        self._focused_widget = None
        self._listeners.clear()
        self._views = WorkspaceFocusViews(())
