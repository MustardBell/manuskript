"""Showing a surface in the window's central pages, by widget identity.

The container this is written against is the tab widget MainWindow already
has and already hides the tab bar of: the navigator drives it, and it is
the page side of the navigator rather than a second one.

Every address here is a widget. The old central area was addressed by tab
number, which is why a surface leaving it moved every surface after it and
why `panelIdForLegacyTab` exists to translate saved numbers. A number means
"whatever is in that position now"; a widget means the surface itself.
"""

import pytest

from PyQt5.QtWidgets import QLabel, QTabWidget

from manuskript.panels import NavigatorEntry, WorkspaceSurfaceDescriptor
from manuskript.ui.surface_presentation import CentralSurfacePresentation
from manuskript.ui.workspace_surfaces import (
    WorkspaceSurfaceError,
    WorkspaceSurfaceHost,
    WorkspaceSurfaceInstance,
)


def surface(surface_id, title="Surface"):
    return WorkspaceSurfaceDescriptor(
        id=surface_id,
        title=title,
        widget_factory=lambda context, parent: QLabel(surface_id, parent),
        navigator=NavigatorEntry(label=title),
    )


def an_instance(surface_id, text=None):
    """A surface that has already been built, ready to be shown."""

    return WorkspaceSurfaceInstance(
        descriptor=surface(surface_id),
        widget=QLabel(text or surface_id),
    )


def a_presentation():
    return CentralSurfacePresentation(QTabWidget())


def test_a_mounted_surface_is_in_the_pages():
    presentation = a_presentation()
    instance = an_instance("core.editor")

    presentation.mount(instance)

    assert presentation.pages.indexOf(instance.widget) != -1


def test_nothing_wraps_a_surface_here():
    """The pages hold the widget itself, so there is no container to keep.

    A dock mount answers with the dock it built. This one answers None
    rather than with the pages, because the pages are not this surface's:
    handing every instance the same object back would read as one each.
    """

    presentation = a_presentation()

    assert presentation.mount(an_instance("core.editor")) is None


def test_the_tab_bar_stays_hidden():
    """One navigator, not two.

    The navigator list on the left is what chooses a surface. A row of tabs
    over the same seven surfaces is a second control for the same choice,
    which is how the two came apart before: Characters left the tab widget
    when it became a dock and the navigator kept listing it.
    """

    presentation = a_presentation()

    presentation.mount(an_instance("core.editor"))
    presentation.mount(an_instance("core.outline"))

    # isHidden rather than isVisible: nothing in this test is on screen, so
    # isVisible is False for a tab bar nobody hid and the assertion would
    # pass without the presentation doing anything at all.
    assert presentation.pages.tabBar().isHidden()


def test_mounting_does_not_change_what_is_showing():
    """Arriving is not the same as being asked for.

    Which surface is current belongs to the host; a presentation that
    stole it would make "which one is showing" depend on the order the
    workspace happened to build things in.
    """

    presentation = a_presentation()
    editor = an_instance("core.editor")
    presentation.mount(editor)
    presentation.activate(editor)

    presentation.mount(an_instance("core.outline"))

    assert presentation.pages.currentWidget() is editor.widget


def test_a_page_that_was_there_first_keeps_its_position():
    """Surfaces are appended, so nothing already addressed by number moves.

    The debug page is still reached by index, from `NAVIGATOR_PAGES`. If
    mounting inserted anywhere but the end, that index would silently come
    to mean a surface instead.
    """

    presentation = a_presentation()
    debug = QLabel("debug")
    presentation.pages.addTab(debug, "Debug")

    presentation.mount(an_instance("core.editor"))
    presentation.mount(an_instance("core.outline"))

    assert presentation.pages.indexOf(debug) == 0


def test_activating_shows_the_widget_asked_for():
    presentation = a_presentation()
    editor = an_instance("core.editor")
    outline = an_instance("core.outline")
    presentation.mount(editor)
    presentation.mount(outline)

    presentation.activate(outline)

    assert presentation.pages.currentWidget() is outline.widget


def test_activating_survives_the_positions_shifting():
    """The point of addressing by widget.

    Removing a surface moves everything after it. An implementation that
    kept the number it was mounted at would show the wrong surface here --
    and would be right until the first time somebody closed one.
    """

    presentation = a_presentation()
    general = an_instance("core.general")
    editor = an_instance("core.editor")
    outline = an_instance("core.outline")
    for instance in (general, editor, outline):
        presentation.mount(instance)

    presentation.unmount(general)
    presentation.activate(outline)

    assert presentation.pages.currentWidget() is outline.widget


def test_activating_one_that_is_not_here_is_refused():
    """Rather than quietly showing whatever was already up.

    Qt's own answer to setCurrentWidget on a stranger is to do nothing,
    which leaves the host saying one surface is current while the reader
    is looking at another -- the divergence that has already been fixed
    once inside the host.
    """

    presentation = a_presentation()
    presentation.mount(an_instance("core.editor"))

    with pytest.raises(WorkspaceSurfaceError, match="not mounted"):
        presentation.activate(an_instance("core.outline"))


def test_unmounting_takes_it_out_of_the_pages():
    presentation = a_presentation()
    instance = an_instance("core.editor")
    presentation.mount(instance)

    presentation.unmount(instance)

    assert presentation.pages.indexOf(instance.widget) == -1
    assert presentation.pages.count() == 0


def test_an_unmounted_surface_is_alive_and_belongs_to_nobody():
    """It is being moved, not closed.

    Qt keeps a removed page as a child of the container it was removed
    from. A surface handed to another window while still parented here
    would be destroyed with this window -- the writer's editor, with work
    in it, dying because the window it used to be in closed.
    """

    presentation = a_presentation()
    instance = an_instance("core.editor", text="half a chapter")
    presentation.mount(instance)

    presentation.unmount(instance)

    assert instance.widget.parent() is None
    assert instance.widget.text() == "half a chapter"


def test_unmounting_something_that_is_not_here_does_nothing():
    """Detaching twice must not raise. The second one has nothing to undo."""

    presentation = a_presentation()

    presentation.unmount(an_instance("core.editor"))

    assert presentation.pages.count() == 0


def test_one_presentation_cannot_take_a_surface_out_of_another():
    """Only the container that took a surface in may let it go.

    Releasing a widget this container never held would tear it out of the
    window that does hold it, from a window that has nothing to do with
    it -- and the reader would watch a surface vanish somewhere they were
    not even looking.
    """

    holder = a_presentation()
    stranger = a_presentation()
    instance = an_instance("core.editor")
    holder.mount(instance)

    stranger.unmount(instance)

    assert holder.pages.indexOf(instance.widget) != -1
    assert instance.widget.parent() is not None


def test_a_host_backed_by_the_pages_shows_what_it_opens():
    """The two halves against each other, with no fake in between.

    The host's own tests use a presentation that is neither a stack nor a
    dock, deliberately. This one proves the port they were written against
    is the port this implements.
    """

    from manuskript.panels import PanelRegistry

    registry = PanelRegistry()
    registry.register(surface("core.editor"))
    registry.register(surface("core.outline"))
    presentation = a_presentation()
    host = WorkspaceSurfaceHost(registry, presentation)

    editor = host.open("core.editor")
    host.open("core.outline")

    assert presentation.pages.currentWidget() is editor.widget

    outline = host.instance("core.outline")
    host.activate("core.outline")

    assert presentation.pages.currentWidget() is outline.widget

    host.detach("core.outline")

    assert presentation.pages.currentWidget() is editor.widget
    assert outline.widget.parent() is None
