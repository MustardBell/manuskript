"""How a panel is fastened into a window, one class per way.

There are two ways -- a slot in a named splitter, a dock around the
document -- and the host used to spell both out wherever it needed one.
Opening spelled them out twice, adopting a panel from another window a
third time, and tearing one off a fourth, so a dock was built from scratch
in three places that had to agree about its name, its delete-on-close
attribute, and asking Qt to restore its saved position before putting it
anywhere. They did not always agree, and the last time they disagreed a
moved panel's toggle emptied its dock and left the frame standing.

Each mount answers the same three questions instead:

* ``prepare`` -- what a new widget is built into, and what container to
  keep. A dock exists before its widget, because the widget is built as
  its child; a splitter panel has no container at all.
* ``install`` -- put a widget, new or arriving from elsewhere, in place.
* ``discard`` -- undo a prepare whose widget never came.

A third placement would be a third class and nothing else: no branch in
the host changes, because the host looks a mount up by placement rather
than asking which kind it has.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget
from manuskript.panels import DOCK, SPLITTER_SLOT


def dock_name(descriptor):
    """The one name this panel's dock answers to.

    Saved window layouts identify docks by it, so a panel that had one
    before the panel vocabulary existed keeps it.
    """
    return descriptor.object_name or "panel.{}".format(descriptor.id)


class SplitterMount:
    """A panel that sits directly in one of the window's splitters."""

    placement = SPLITTER_SLOT

    def __init__(self, views):
        self.views = views

    def find(self, descriptor):
        """The splitter this panel belongs in, or None if it is not there.

        Answers None rather than raising, because two callers ask merely
        to find out -- remembering a splitter's sizes when a panel leaves
        it, and giving them back when it returns.
        """
        if descriptor.placement != SPLITTER_SLOT or descriptor.slot is None:
            return None
        return self.views.find_splitter(descriptor.slot.splitter)

    def prepare(self, descriptor):
        """The splitter itself is what a new widget is built into."""
        return self._splitter(descriptor), None

    def install(self, descriptor, widget, container=None):
        self._splitter(descriptor).insertWidget(
            descriptor.slot.index, widget,
        )

    def discard(self, container=None):
        """Nothing was made, so nothing has to be unmade."""

    def _splitter(self, descriptor):
        splitter = self.find(descriptor)
        if splitter is None:
            raise LookupError(
                "This window has no splitter named {!r}.".format(
                    descriptor.slot.splitter
                    if descriptor.slot is not None
                    else None
                )
            )
        return splitter


class DockMount:
    """A panel that lives in a dock around the document area."""

    placement = DOCK

    def __init__(self, views):
        self.views = views

    def prepare(self, descriptor):
        """A dock, which is both the widget's parent and its container.

        Its close button puts the panel away; it does not destroy it.
        Delete-on-close here was inherited from the plugin host this
        replaced, and it meant the X on a dock took the panel out of the
        window for good -- the toggle that should bring it back had
        nothing left to show, and anything still holding the panel was
        left holding a deleted widget.
        """
        dock = self.views.create_dock(descriptor.title)
        dock.setObjectName(dock_name(descriptor))
        dock.setAttribute(Qt.WA_DeleteOnClose, False)
        if descriptor.navigator is not None:
            # A surface the navigator offers is a window. It may be docked,
            # and docked it may fill most of the frame, but floating it does
            # not make it a window of its own -- it makes a utility window
            # owned by this one, with no taskbar entry, no minimize or
            # maximize, raising with its owner and unable to hold anything
            # else. Dragging one out looked like making a window and made
            # the opposite, so Qt is not offered the chance.
            dock.setFeatures(
                dock.features() & ~QDockWidget.DockWidgetFloatable
            )
        return dock, dock

    def install(self, descriptor, widget, container):
        container.setWidget(widget)
        self.place(container)

    def install_floating(self, descriptor, widget, container):
        """A dock standing free of the layout.

        Under the same object name as when it is docked. A panel is one
        thing whether it floats or not, and Qt records floating state
        against the name -- two names would mean a panel left floating
        came back docked, having saved its geometry under a name nothing
        would look for again.
        """
        container.setWidget(widget)
        container.setFloating(True)

    def discard(self, container):
        if container is not None:
            container.deleteLater()

    def place(self, dock, default_area=Qt.RightDockWidgetArea):
        """Put a dock where the person last left it, if that is known.

        Panels are built when they are asked for, which is long after the
        window applied its saved layout -- and QMainWindow.restoreState
        can only place docks that existed when it ran. So every dock
        created later asks to be restored by name, and falls back to the
        default area when the layout has never seen it.
        """
        # Asked for by name before being put anywhere. Adding it to an
        # area first commits it there and makes the restore silently do
        # nothing -- it still reports success, which is how this looked
        # like Qt ignoring us rather than us asking too late.
        #
        # This is also all that is needed for a panel whose plugin is
        # temporarily away. QMainWindow.saveState keeps the entry for a
        # dock it restored but never found, and keeps it across any
        # number of further sessions, so the place is held without our
        # help: measured over three saves with the dock absent, then
        # restored to the same area when it came back. No placeholder
        # dock scheme is required, and building one would put a widget
        # on screen to solve a problem Qt has already solved.
        if self.views.restore_dock(dock):
            return True
        # A dock the saved layout has never seen: it goes where panels
        # of its kind go.
        self.views.add_dock(default_area, dock)
        return False


def mounts_for(views):
    """Every way this workspace can fasten a panel, by placement."""
    return {
        mount.placement: mount
        for mount in (SplitterMount(views), DockMount(views))
    }
