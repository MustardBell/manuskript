"""Independent native presentation for workspace-owned surfaces."""

from types import SimpleNamespace

import pytest

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from manuskript.panels import NavigatorEntry, WorkspaceSurfaceDescriptor
from manuskript.ui.surface_presentation import DockSurfacePresentation
from manuskript.ui.workspace_surfaces import (
    WorkspaceSurfaceError,
    WorkspaceSurfaceInstance,
)


class Dock:
    def __init__(self, title):
        self.title = title
        self.name = ""
        self.widget = None
        self.visible = None
        self.parent = object()
        self.deleted = False

    def setObjectName(self, name):
        self.name = name

    def setAttribute(self, _attribute, _value):
        pass

    def setWidget(self, widget):
        self.widget = widget
        widget.setParent(None)

    def setVisible(self, visible):
        self.visible = bool(visible)

    def setParent(self, parent):
        self.parent = parent

    def deleteLater(self):
        self.deleted = True


class Views:
    def __init__(self, restore=False):
        self.restore = restore
        self.created = []
        self.added = []
        self.removed = []
        self.activated = []

    def create_dock(self, title):
        dock = Dock(title)
        self.created.append(dock)
        return dock

    def restore_dock(self, _dock):
        return self.restore

    def add_dock(self, area, dock):
        self.added.append((area, dock))

    def remove_dock(self, dock):
        self.removed.append(dock)

    def activate_dock(self, dock):
        self.activated.append(dock)


def an_instance(surface_id, visible=False):
    descriptor = WorkspaceSurfaceDescriptor(
        id=surface_id,
        title="Surface",
        default_visible=visible,
        widget_factory=lambda context, parent: QLabel(surface_id, parent),
        navigator=NavigatorEntry(label="Surface"),
    )
    return WorkspaceSurfaceInstance(
        descriptor=descriptor,
        widget=QLabel(surface_id),
    )


def test_each_surface_gets_its_own_native_container():
    views = Views()
    presentation = DockSurfacePresentation(views)
    editor = an_instance("core.editor")
    outline = an_instance("core.outline")

    editor_dock = presentation.mount(editor)
    outline_dock = presentation.mount(outline)

    assert editor_dock is not outline_dock
    assert editor_dock.widget is editor.widget
    assert outline_dock.widget is outline.widget
    assert editor_dock.name == "panel.core.editor"
    assert outline_dock.name == "panel.core.outline"
    assert views.added == [
        (Qt.RightDockWidgetArea, editor_dock),
        (Qt.RightDockWidgetArea, outline_dock),
    ]


def test_mounting_does_not_steal_default_visibility():
    views = Views()
    presentation = DockSurfacePresentation(views)

    hidden = presentation.mount(an_instance("core.editor"))
    shown = presentation.mount(an_instance("core.general", visible=True))

    assert hidden.visible is False
    assert shown.visible is True


def test_a_restored_container_is_not_added_to_a_fallback_area():
    views = Views(restore=True)
    presentation = DockSurfacePresentation(views)

    presentation.mount(an_instance("core.editor"))

    assert views.added == []


def test_activation_targets_the_surface_own_container():
    views = Views()
    presentation = DockSurfacePresentation(views)
    editor = an_instance("core.editor")
    outline = an_instance("core.outline")
    editor.container = presentation.mount(editor)
    outline.container = presentation.mount(outline)

    presentation.activate(outline)

    assert views.activated == [outline.container]


def test_unmount_preserves_the_living_widget_for_transfer():
    views = Views()
    presentation = DockSurfacePresentation(views)
    instance = an_instance("core.editor")
    instance.container = presentation.mount(instance)
    old_dock = instance.container

    presentation.unmount(instance)

    assert instance.widget.parent() is None
    assert instance.widget.text() == "core.editor"
    assert views.removed == [old_dock]
    assert old_dock.parent is None
    assert old_dock.deleted


def test_one_presentation_cannot_remove_another_workspace_surface():
    owner_views = Views()
    owner = DockSurfacePresentation(owner_views)
    stranger_views = Views()
    stranger = DockSurfacePresentation(stranger_views)
    instance = an_instance("core.editor")
    instance.container = owner.mount(instance)

    stranger.unmount(instance)

    assert stranger_views.removed == []
    assert instance.container.widget is instance.widget


def test_one_presentation_cannot_activate_another_workspace_surface():
    owner = DockSurfacePresentation(Views())
    stranger = DockSurfacePresentation(Views())
    instance = an_instance("core.editor")
    instance.container = owner.mount(instance)

    with pytest.raises(WorkspaceSurfaceError, match="no dock"):
        stranger.activate(instance)


def test_the_obsolete_central_stack_is_not_an_available_presentation():
    import manuskript.ui.surface_presentation as module

    assert not hasattr(module, "CentralSurfacePresentation")
