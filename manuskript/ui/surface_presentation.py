"""How a workspace shows the surfaces it holds.

``WorkspaceSurfaceHost`` says which surfaces a workspace has and which one
is showing. It deliberately does not say what showing looks like: that is a
presentation, injected, and the host's tests use one that is neither a
stack nor a dock so that nothing asserts the arrangement they were written
against.

The production presentation uses independent native docks.  A dock is a
presentation of a surface, not its domain identity: the surface host still
owns the living widget and can transfer it intact between workspaces.  This
keeps every writing surface independently visible, movable and floatable
without conflating it with a tool-panel contribution.

Every address here is a widget. The old central area was addressed by tab
number -- which is why removing a surface moved every surface after it, and
why saved numbers need ``panelIdForLegacyTab`` to be read at all. A number
means "whatever is in that position now". A widget means the surface.

The port is ``mount(instance) -> container``, ``unmount(instance)`` and
``activate(instance)``.
"""

from PyQt5.QtCore import Qt

from manuskript.ui.panels.mounts import dock_name
from manuskript.ui.workspace_surfaces import WorkspaceSurfaceError


class DockSurfacePresentation:
    """Present each living surface in its own native ``QDockWidget``.

    ``views`` is the same narrow window port used by panel mounting.  The
    presentation deliberately does not use ``PanelHost``: surface ownership,
    bindings and transfer remain in ``WorkspaceSurfaceHost`` while Qt docking
    is only the way that owner displays a surface in this window.
    """

    def __init__(self, views, default_area=Qt.RightDockWidgetArea):
        self.views = views
        self.default_area = default_area
        self.on_mounted = None
        self.on_unmounted = None
        self._containers = {}

    def mount(self, instance):
        descriptor = instance.descriptor
        dock = self.views.create_dock(descriptor.title)
        dock.setObjectName(dock_name(descriptor))
        dock.setAttribute(Qt.WA_DeleteOnClose, False)
        dock.setWidget(instance.widget)
        # All canonical surfaces exist before window-state restoration, so a
        # new one only needs a fallback area. A transferred/plugin surface
        # may arrive later and can still reclaim a saved place by objectName.
        restored = self.views.restore_dock(dock)
        if not restored:
            self.views.add_dock(self.default_area, dock)
        dock.setVisible(bool(descriptor.default_visible))
        self._containers[id(instance)] = dock
        if callable(self.on_mounted):
            self.on_mounted(instance, dock)
        return dock

    def unmount(self, instance):
        dock = instance.container
        if (
            dock is None
            or self._containers.get(id(instance)) is not dock
        ):
            return
        if callable(self.on_unmounted):
            self.on_unmounted(instance, dock)
        # Tell QDockWidget that it no longer owns content before reparenting
        # the living surface. Reparenting the child directly happens to look
        # sufficient for an ordinary dock, but leaves QDockWidget's private
        # layout pointing at content that has already left. Removing a native
        # floating dock in that state can crash below SIP rather than raise a
        # Python exception. Tool-panel transfer uses the same Qt API boundary.
        dock.setWidget(None)
        instance.widget.setParent(None)
        self.views.remove_dock(dock)
        dock.setParent(None)
        dock.deleteLater()
        self._containers.pop(id(instance), None)

    def activate(self, instance):
        dock = instance.container
        if (
            dock is None
            or self._containers.get(id(instance)) is not dock
        ):
            raise WorkspaceSurfaceError(
                "{} has no dock in this workspace.".format(instance.id)
            )
        self.views.activate_dock(dock)

    def dispose(self):
        self.on_mounted = None
        self.on_unmounted = None
        self._containers.clear()
        self.views = None
