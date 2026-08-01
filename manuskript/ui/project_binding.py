from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.project_context_binding import ProjectContextBinding
from manuskript.ui.project_feature_binding import ProjectFeatureBinding
from manuskript.ui.project_view_binding import (
    DebugProjectBinding,
    FlatDataProjectBinding,
    OutlineSelectionProjectBinding,
)


class ProjectBinding:
    """Own the complete UI binding lifecycle for one active project."""

    def __init__(self, window):
        self.connections = SignalConnectionRegistry()
        self.flat_data = FlatDataProjectBinding(window)
        self.features = ProjectFeatureBinding(window)
        self.contexts = ProjectContextBinding(window)
        self.outline_selection = OutlineSelectionProjectBinding(window)
        self.debug_views = DebugProjectBinding(window)
        self.bound = False

    @property
    def reference_service(self):
        return self.contexts.reference_service

    @property
    def text_editor_context(self):
        return self.contexts.text_editor_context

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
        self.contexts.unbind()
        self.features.unbind()
        self.bound = False
