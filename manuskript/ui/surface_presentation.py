"""How a workspace shows the surfaces it holds.

``WorkspaceSurfaceHost`` says which surfaces a workspace has and which one
is showing. It deliberately does not say what showing looks like: that is a
presentation, injected, and the host's tests use one that is neither a
stack nor a dock so that nothing asserts the arrangement they were written
against.

This is the first production one. It shows a surface in the window's
central pages -- the tab widget MainWindow already has, whose tab bar it
already hides and whose current page the navigator already sets. Central
because the complaint that started this was that surfaces are narrow: they
were built for the 230 pixels a dock gave them, and they are supposed to be
windows. Whether centrality reproduces upstream's *frame* is a separate
question the parity oracle answers by running upstream, not one this class
assumes.

Every address here is a widget. The old central area was addressed by tab
number -- which is why removing a surface moved every surface after it, and
why saved numbers need ``panelIdForLegacyTab`` to be read at all. A number
means "whatever is in that position now". A widget means the surface.

The port is ``mount(instance) -> container``, ``unmount(instance)`` and
``activate(instance)``.
"""

from manuskript.ui.workspace_surfaces import WorkspaceSurfaceError


class CentralSurfacePresentation:
    """Surfaces shown as pages of one container, one of them current.

    ``pages`` is a ``QTabWidget``. Its tab bar is hidden and stays hidden:
    the navigator list is what chooses a surface, and a row of tabs over
    the same surfaces would be a second control for the same choice. That
    is not hypothetical -- the navigator and the tab widget already came
    apart once, when Characters became a dock and left the tabs while the
    navigator went on listing it.
    """

    def __init__(self, pages):
        self.pages = pages
        self.pages.tabBar().hide()

    def mount(self, instance):
        """Put a surface in the pages without showing it.

        Appended, never inserted: the debug page is still reached by the
        index in ``NAVIGATOR_PAGES``, and inserting ahead of it would make
        that number quietly mean a surface instead.

        Arriving is not being asked for, and appending is what keeps those
        apart: Qt only makes a new page current when there was no current
        page. Which surface is showing is the host's to say -- it settles
        that explicitly -- and a mount that decided it would make what a
        reader sees depend on the order the workspace built things in.

        Answers None because nothing here wraps the surface. The pages hold
        the widget itself, and handing back the container they all share
        would read as one each.
        """

        self.pages.addTab(instance.widget, instance.descriptor.title)
        return None

    def unmount(self, instance):
        """Take a surface out, alive and belonging to nobody.

        Qt keeps a removed page as a child of the container it came out
        of. A surface handed to another window while still parented here
        would be destroyed with this one -- the writer's editor, with work
        in it, dying because the window it used to be in closed.

        Silent about a surface that is not here: detaching what was
        already detached has nothing to undo.
        """

        position = self.pages.indexOf(instance.widget)
        if position == -1:
            return
        self.pages.removeTab(position)
        instance.widget.setParent(None)

    def activate(self, instance):
        """Show this one.

        Refuses a surface it does not hold rather than doing what Qt does,
        which is nothing: that leaves the host saying one surface is
        current while the reader is looking at another. The host has
        already had that divergence fixed inside it once, and a
        presentation that answered quietly would put it straight back.
        """

        position = self.pages.indexOf(instance.widget)
        if position == -1:
            raise WorkspaceSurfaceError(
                "{} is not mounted in these pages, so it cannot be "
                "shown.".format(instance.id)
            )
        self.pages.setCurrentIndex(position)
