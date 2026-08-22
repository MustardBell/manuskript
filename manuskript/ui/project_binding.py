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
        self.surfaceInstances = views.surface_instances
        # Built at bind time, because a window has no models to bind
        # until a project is open -- and injectable, so what the context
        # binding is given is one decision made in one place.
        self.contextsFactory = contexts_factory
        self.contexts = None
        self.bound = False
        self._surfaces = {}

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
            for instance in self._surface_instances():
                self._attach_surface(instance)
        except Exception:
            for instance in reversed(tuple(self._surfaces.values())):
                self._detach_surface(instance)
            self.connections.disconnect_all()
            if contexts_started:
                self.contexts.unbind()
            self.features.unbind()
            self.flat_data.unbind()
            raise
        self.bound = True

    def _surface_instances(self):
        return self.surfaceInstances()

    def attach_surface(self, instance):
        if self.bound:
            self._attach_surface(instance)

    def detach_surface(self, instance):
        if self.bound:
            self._detach_surface(instance)

    def _attach_surface(self, instance):
        if instance.id in self._surfaces:
            return
        attached = []
        try:
            for binding in (
                self.flat_data,
                self.contexts,
                self.outline_selection,
            ):
                binding.attach_surface(instance)
                attached.append(binding)
        except Exception:
            for binding in reversed(attached):
                binding.detach_surface(instance)
            raise
        self._surfaces[instance.id] = instance

    def _detach_surface(self, instance):
        if self._surfaces.pop(instance.id, None) is None:
            return
        self.outline_selection.detach_surface(instance)
        self.contexts.detach_surface(instance)
        self.flat_data.detach_surface(instance)

    def unbind(self):
        if not self.bound:
            return

        # Stop callbacks before clearing the objects they depend on.
        for instance in reversed(tuple(self._surfaces.values())):
            self._detach_surface(instance)
        self.connections.disconnect_all()
        if self.contexts is not None:
            self.contexts.unbind()
        self.features.unbind()
        self.flat_data.unbind()
        self.outline_selection.unbind()
        self.bound = False

    def dispose(self):
        """Release stable workspace views after their project unbinds."""
        self.unbind()
        self.connections.disconnect_all()
        self.flat_data.views = None
        self.outline_selection.views = None
        self.debug_views.views = None
        self.features.dispose()
        self.features = None
        self.contexts = None
        self.contextsFactory = None
        self.surfaceInstances = None
