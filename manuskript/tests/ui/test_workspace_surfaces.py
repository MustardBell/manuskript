"""Which surfaces a workspace holds, and what moving one between them means."""

import pytest

from manuskript.panels import (
    NavigatorEntry,
    PanelRegistry,
    WorkspaceSurfaceDescriptor,
)
from manuskript.ui.workspace_surfaces import (
    WorkspaceSurfaceError,
    WorkspaceSurfaceHost,
)


class Widget:
    """Stands in for a surface's widget without needing Qt."""

    def __init__(self, name):
        self.name = name
        self.parent = object()
        self.showing = "whatever the writer was looking at"

    def setParent(self, parent):
        self.parent = parent


class Presentation:
    """Somewhere to put a surface, recording what it was asked to do.

    Deliberately not a stack or a dock: the host must work either way, and
    a test that needed one of them would be asserting the presentation this
    was written against rather than the host's own contract.
    """

    def __init__(self):
        self.shown = []
        self.removed = []
        self.raised = []

    def show(self, instance):
        self.shown.append(instance.id)
        return "container-for-{}".format(instance.id)

    def remove(self, instance):
        self.removed.append(instance.id)

    def raise_(self, instance):
        self.raised.append(instance.id)

    def hide(self, instance):
        pass


def surface(surface_id, title="Surface", factory=None):
    return WorkspaceSurfaceDescriptor(
        id=surface_id,
        title=title,
        widget_factory=factory or (lambda context, parent: Widget(surface_id)),
        navigator=NavigatorEntry(label=title),
    )


def a_host(*descriptors):
    registry = PanelRegistry()
    for descriptor in descriptors:
        registry.register(descriptor)
    return WorkspaceSurfaceHost(registry, Presentation())


def test_a_workspace_holds_only_the_surfaces_it_was_asked_for():
    """Not one of everything that exists.

    A workspace building every surface it had heard of is what made a second
    window construct its own Editor, leaving a move nothing to hand over.
    Which surfaces this workspace has is something it states.
    """

    host = a_host(surface("core.editor"), surface("core.outline"))

    host.open("core.editor")

    assert host.contains("core.editor")
    assert not host.contains("core.outline")


def test_opening_the_same_surface_twice_gives_the_same_one():
    host = a_host(surface("core.editor"))

    first = host.open("core.editor")
    second = host.open("core.editor")

    assert first is second
    assert host.presentation.shown == ["core.editor"]


def test_only_open_may_build_one():
    """Reading must never construct.

    A property that builds a widget is a thread-affinity hazard advertising
    nothing, and it makes membership a consequence of what happened to be
    touched first rather than something the workspace says.
    """

    built = []
    host = a_host(surface(
        "core.editor",
        factory=lambda context, parent: built.append(1) or Widget("editor"),
    ))

    host.contains("core.editor")
    host.instance("core.editor")
    host.current()
    host.activate("core.editor")

    assert built == []

    host.open("core.editor")

    assert built == [1]


def test_a_surface_with_no_factory_is_refused_rather_than_half_built():
    host = a_host(WorkspaceSurfaceDescriptor(id="core.ghost", title="Ghost"))

    with pytest.raises(WorkspaceSurfaceError, match="no factory"):
        host.open("core.ghost")


def test_moving_a_surface_carries_the_living_widget():
    """Not a rebuild: what it was showing has to survive the move.

    This is the whole reason a detach is not "close here, open there". The
    reader tore the editor out with work in it.
    """

    source = a_host(surface("core.editor"))
    destination = a_host(surface("core.editor"))
    opened = source.open("core.editor")
    opened.widget.showing = "half a chapter"

    moved = source.detach("core.editor")
    destination.attach(moved)

    assert destination.instance("core.editor").widget is opened.widget
    assert destination.instance("core.editor").widget.showing == "half a chapter"
    assert not source.contains("core.editor")
    assert destination.presentation.shown == ["core.editor"]


def test_a_detached_surface_belongs_to_nobody_until_it_is_attached():
    source = a_host(surface("core.editor"))
    source.open("core.editor")

    moved = source.detach("core.editor")

    assert moved.host is None
    assert moved.container is None
    assert source.presentation.removed == ["core.editor"]


def test_a_workspace_that_already_holds_one_refuses_the_second():
    """Refused rather than silently replacing what is there.

    Two presentations of one surface in one workspace is the state where
    "which one is showing" stops having an answer.
    """

    source = a_host(surface("core.editor"))
    destination = a_host(surface("core.editor"))
    destination.open("core.editor")

    with pytest.raises(WorkspaceSurfaceError, match="already holds"):
        destination.attach(source.open("core.editor"))


def test_activating_shows_the_one_asked_for():
    host = a_host(surface("core.editor"), surface("core.outline"))
    host.open("core.editor")
    host.open("core.outline")

    host.activate("core.outline")

    assert host.current() == "core.outline"
    assert host.presentation.raised == ["core.outline"]


def test_activating_something_this_workspace_does_not_hold_does_nothing():
    """It is not here. Building it would be a different request."""

    host = a_host(surface("core.editor"))

    assert host.activate("core.editor") is None
    assert host.current() is None


def test_the_first_surface_opened_is_the_one_showing():
    host = a_host(surface("core.editor"), surface("core.outline"))

    host.open("core.editor")
    host.open("core.outline")

    assert host.current() == "core.editor"


def test_letting_the_current_surface_go_leaves_another_showing():
    host = a_host(surface("core.editor"), surface("core.outline"))
    host.open("core.editor")
    host.open("core.outline")

    host.detach("core.editor")

    assert host.current() == "core.outline"


def test_closing_the_last_surface_leaves_nothing_showing():
    host = a_host(surface("core.editor"))
    host.open("core.editor")

    assert host.close("core.editor")
    assert host.current() is None
    assert not host.contains("core.editor")
