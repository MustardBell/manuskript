"""Focused command targets owned by one workspace window."""

from dataclasses import dataclass
from typing import Any, Tuple
from weakref import WeakMethod, ref

from PyQt5 import sip

from manuskript.panels.core import EDITOR
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
        self._surface_targets = {}
        self._document_target = None
        self._markup_target = None
        self._focused_widget = None
        self._listeners = []

    @property
    def document_target(self):
        return self._document_target

    @property
    def markup_target(self):
        return self._live_target("_markup_target")

    def current_document_target(self):
        """Return the endpoint used by document command routing."""
        return self._document_target

    def current_markup_target(self):
        """Return the endpoint used by markup command routing."""
        return self._live_target("_markup_target")

    @property
    def focused_widget(self):
        return self._live_target("_focused_widget")

    def _live_target(self, attribute):
        target = getattr(self, attribute)
        if target is None:
            return None
        try:
            deleted = sip.isdeleted(target)
        except TypeError:
            # Unit-test doubles and non-QObject command roots are alive by
            # ordinary Python ownership rather than by a SIP wrapper.
            deleted = False
        if not deleted:
            return target
        setattr(self, attribute, None)
        if attribute == "_focused_widget":
            self._markup_target = None
        return None

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
        # A native focus event reports synchronously through the editor port;
        # QApplication may then publish the same transition globally. One
        # transition must not notify pane/history listeners twice.
        if new is not None and self.focused_widget is new:
            return
        self._focused_widget = new
        self._markup_target = self._find_markdown_editor(new)

        candidate = new
        while candidate is not None:
            if candidate in self._document_targets():
                self._document_target = candidate
                break
            candidate = candidate.parent()

        listeners = []
        callbacks = []
        for listener_ref in self._listeners:
            listener = listener_ref()
            if listener is not None and self._listener_is_alive(listener):
                listeners.append(listener_ref)
                callbacks.append(listener)
        self._listeners = listeners
        for listener in callbacks:
            listener(_old, new)

    def attach_surface(self, instance):
        """Adopt the focus endpoints contributed by one surface."""

        if instance.id != EDITOR:
            return
        editor = instance.widget.editor
        self._surface_targets[instance.id] = editor
        editor.set_focus_source(self)

    def detach_surface(self, instance):
        """Release endpoints before their surface leaves this workspace."""

        target = self._surface_targets.pop(instance.id, None)
        if target is None:
            return
        target.set_focus_source(None)
        if self._document_target is target:
            self._document_target = None
        focused = self.focused_widget
        candidate = focused
        while candidate is not None:
            if candidate is target:
                self._focused_widget = None
                self._markup_target = None
                break
            candidate = candidate.parent()

    def _document_targets(self):
        return self._views.document_targets + tuple(
            self._surface_targets.values()
        )

    @staticmethod
    def _listener_is_alive(listener):
        """Whether a weak Python receiver still has a native Qt object.

        A QObject wrapper can outlive the C++ object owned by its parent.
        WeakMethod still resolves in that interval, but invoking a signal on
        the receiver raises ``RuntimeError``. Treat native death exactly like
        ordinary weak-reference death and prune the observer.
        """
        owner = getattr(listener, "__self__", None)
        if owner is None:
            return True
        try:
            return not sip.isdeleted(owner)
        except TypeError:
            return True

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
        for target in self._surface_targets.values():
            target.set_focus_source(None)
        self._document_target = None
        self._markup_target = None
        self._focused_widget = None
        self._listeners.clear()
        self._surface_targets.clear()
        self._views = WorkspaceFocusViews(())
