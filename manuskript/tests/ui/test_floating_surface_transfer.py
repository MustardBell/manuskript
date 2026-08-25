"""A torn-off writing surface becomes a peer workspace, not a utility."""

from types import SimpleNamespace

from manuskript.ui.surface_transfer import (
    FloatingSurfaceTransferController,
    FloatingSurfaceTransferViews,
)


class Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def disconnect(self, slot):
        self.slots.remove(slot)

    def emit(self, value):
        for slot in tuple(self.slots):
            slot(value)


class Dock:
    def __init__(self):
        self.topLevelChanged = Signal()
        self.floating = False
        self.geometry = object()
        self.updates_enabled = True

    def isFloating(self):
        return self.floating

    def setFloating(self, value):
        self.floating = bool(value)
        self.topLevelChanged.emit(self.floating)

    def frameGeometry(self):
        return self.geometry

    def setUpdatesEnabled(self, enabled):
        self.updates_enabled = bool(enabled)


class Host:
    def __init__(self, instances):
        self.instances = dict(instances)

    def instance(self, surface_id):
        return self.instances.get(surface_id)


def controller_for(host, move):
    deferred = []
    placed = []
    statuses = []
    controller = FloatingSurfaceTransferController(
        FloatingSurfaceTransferViews(
            host=host,
            project_active=lambda: True,
            move_to_new_workspace=move,
            place_workspace=lambda workspace, geometry: placed.append(
                (workspace, geometry)
            ),
            show_status=lambda *message: statuses.append(message),
            translate=lambda text: text,
            defer=deferred.append,
        )
    )
    return controller, deferred, placed, statuses


def test_floating_a_surface_moves_the_living_instance_to_a_real_workspace():
    dock = Dock()
    editor = SimpleNamespace(id="core.editor", container=dock)
    host = Host({"core.editor": editor, "core.general": object()})
    workspace = SimpleNamespace(
        shown=0,
        raised=0,
        activated=0,
        show=lambda: setattr(workspace, "shown", workspace.shown + 1),
        raise_=lambda: setattr(workspace, "raised", workspace.raised + 1),
        activateWindow=lambda: setattr(
            workspace, "activated", workspace.activated + 1
        ),
    )
    moved = []

    def move(surface_id):
        moved.append(surface_id)
        host.instances.pop(surface_id)
        return workspace

    controller, deferred, placed, _statuses = controller_for(host, move)
    controller.attach_surface(editor)

    dock.setFloating(True)

    assert moved == []
    assert len(deferred) == 1
    deferred.pop()()
    assert moved == []
    assert not dock.isFloating()
    assert not dock.updates_enabled
    assert len(deferred) == 1
    deferred.pop()()
    assert moved == ["core.editor"]
    assert placed == [(workspace, dock.geometry)]
    assert (workspace.shown, workspace.raised, workspace.activated) == (1, 1, 1)


def test_a_surface_already_alone_in_a_workspace_is_docked_back():
    dock = Dock()
    editor = SimpleNamespace(id="core.editor", container=dock)
    host = Host({"core.editor": editor})
    moved = []
    controller, deferred, _placed, statuses = controller_for(
        host, lambda surface_id: moved.append(surface_id)
    )
    controller.attach_surface(editor)

    dock.setFloating(True)
    deferred.pop()()

    assert not dock.isFloating()
    assert moved == []
    assert statuses


def test_failed_transfer_restores_the_normalized_source_dock():
    dock = Dock()
    editor = SimpleNamespace(id="core.editor", container=dock)
    host = Host({"core.editor": editor, "core.general": object()})
    controller, deferred, _placed, _statuses = controller_for(
        host, lambda _surface_id: None
    )
    controller.attach_surface(editor)

    dock.setFloating(True)
    deferred.pop()()
    deferred.pop()()

    assert not dock.isFloating()
    assert dock.updates_enabled
    assert host.instance("core.editor") is editor


def test_a_surface_that_leaves_disconnects_its_old_dock():
    dock = Dock()
    editor = SimpleNamespace(id="core.editor", container=dock)
    host = Host({"core.editor": editor, "core.general": object()})
    controller, deferred, _placed, _statuses = controller_for(
        host, lambda _surface_id: None
    )
    controller.attach_surface(editor)
    controller.detach_surface(editor)

    dock.setFloating(True)

    assert deferred == []
