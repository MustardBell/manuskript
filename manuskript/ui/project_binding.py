from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.project_view_binding import (
    DebugProjectBinding,
    FlatDataProjectBinding,
    OutlineSelectionProjectBinding,
)


class ProjectBinding:
    """Own the complete UI binding lifecycle for one active project."""

    def __init__(self, views, runtime, features, contexts_factory):
        # The views name only the widgets each binding owns; the runtime
        # resolves the model set afresh whenever a project is bound.
        self.connections = SignalConnectionRegistry()
        self.flat_data = FlatDataProjectBinding(views.flat_data, runtime)
        self.features = features
        self.outline_selection = OutlineSelectionProjectBinding(
            views.outline_selection,
        )
        self.debug_views = DebugProjectBinding(views.debug, runtime)
        # Built at bind time, because a window has no models to bind
        # until a project is open -- and injectable, so what the context
        # binding is given is one decision made in one place.
        self.contextsFactory = contexts_factory
        self.contexts = None
        self.bound = False

    @property
    def reference_service(self):
        return (
            self.contexts.reference_service
            if self.contexts is not None
            else None
        )

    @property
    def text_editor_context(self):
        return (
            self.contexts.text_editor_context
            if self.contexts is not None
            else None
        )

    def bind(self):
        if self.bound or self.connections:
            raise RuntimeError(
                "Project UI must be released before rebinding."
            )

        connect = self.connections.connect
        contexts_started = False
        try:
            self.flat_data.bind(connect)
            self.features.bind(connect)
            self.contexts = self.contextsFactory()
            contexts_started = True
            self.contexts.bind(connect)
            self.outline_selection.bind(connect)
            self.debug_views.bind(connect)
        except Exception:
            self.connections.disconnect_all()
            if contexts_started:
                self.contexts.unbind()
            self.features.unbind()
            raise
        self.bound = True

    def unbind(self):
        if not self.bound:
            return

        # Stop callbacks before clearing the objects they depend on.
        self.connections.disconnect_all()
        if self.contexts is not None:
            self.contexts.unbind()
        self.features.unbind()
        self.bound = False
