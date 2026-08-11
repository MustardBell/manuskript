"""The one action that shows and hides a panel, wherever it sits.

Everything that puts a panel on screen -- a toolbar button, a menu entry,
the jump search performs to show its results -- goes through one checkable
action per panel, so no two of them can disagree about what is showing.

Two things make that harder than it sounds, and both are why this is a
class of its own rather than three methods on the host.

What the action drives depends on where the panel is mounted: the dock when
it has one, the widget itself when it sits in a splitter. A panel moved
from a splitter into a dock changes the answer, and the code that mounted
it used to answer from where it stood -- so unchecking a moved panel
emptied its dock and left the frame standing.

And a dock reports its own visibility, which has to be listened to, but
only while it floats. Qt hides a docked widget whenever another tab in the
same area is selected, so treating every invisibility as "the person put
this away" would close a panel merely tabbed behind its neighbour.
"""

from functools import partial
from weakref import ref

from manuskript.ui.connections import weak_callback

class PanelVisibility:
    """One window's panel toggles: what they drive and what drives them."""

    def __init__(self, create_action):
        self._create_action = create_action

    @staticmethod
    def shown_thing(instance):
        """What showing or hiding this panel means where it now sits."""
        if instance.container is not None:
            return instance.container
        return instance.widget

    def bind(self, instance):
        """Give a mounted panel the action that shows and hides it.

        Called after the panel is mounted, never before: what the action
        drives is decided by where the panel ended up.
        """
        descriptor = instance.descriptor
        target = self.shown_thing(instance)
        action = self._create_action(descriptor.title)
        action.setCheckable(True)
        action.setChecked(descriptor.default_visible)
        action.toggled.connect(weak_callback(target.setVisible))
        target.setVisible(descriptor.default_visible)
        if instance.container is not None:
            # By weak reference, and that is the whole point: Qt keeps
            # this callable on the C++ connection, where Python's garbage
            # collector cannot see it. Handing it the instance itself
            # left the dock holding the panel, the panel holding its
            # widget, and the widget holding the window -- so a closed
            # workspace stayed alive with no reference anything could
            # find.
            watch = weak_callback(partial(
                self._container_changed,
                ref(instance),
            ))
            instance.container.visibilityChanged.connect(watch)
            instance.container_watch = watch
        instance.action = action
        return action

    def unbind(self, instance):
        """Stop the toggle driving whatever it was driving.

        The action belongs to this window and goes with it; a host
        adopting the panel makes its own. The dock stops reporting to
        this panel too -- bind made that connection, so unbind is what
        takes it back off.
        """
        watch = instance.container_watch
        instance.container_watch = None
        if watch is not None and instance.container is not None:
            try:
                instance.container.visibilityChanged.disconnect(watch)
            except (RuntimeError, TypeError):
                # Already disconnected, or the dock is gone. Qt raises
                # rather than shrugging.
                pass
        action = instance.action
        if action is None:
            return
        try:
            action.toggled.disconnect()
        except TypeError:
            # Nothing was connected. Qt raises rather than shrugging.
            pass
        action.setEnabled(False)
        instance.action = None

    @staticmethod
    def set_visible(instance, visible=True):
        """Show or hide a panel through its own action.

        Through the action, because that is what every button mirrors;
        poking the widget would leave them all saying otherwise.

        The action can still fall out of step with the panel: restoring
        a window state shows and hides docks itself, without asking any
        of them. An action already reading the way it was asked emits
        nothing, so the panel is set directly in that case -- otherwise
        putting a restored panel away would do nothing at all.
        """
        if instance.action is None:
            return
        if instance.action.isChecked() == visible:
            target = PanelVisibility.shown_thing(instance)
            if target is not None:
                target.setVisible(visible)
            return
        instance.action.setChecked(visible)

    @staticmethod
    def sync(instance):
        """Point a panel's toggle at where the panel actually ended up.

        Called after a bulk restore, which moves docks without going
        through any action, so that every button says what is showing.
        """
        if instance.action is None:
            return
        target = PanelVisibility.shown_thing(instance)
        if target is not None:
            instance.action.setChecked(not target.isHidden())

    def _container_changed(self, instance_reference, visible):
        """Follow a floating dock the person closed with its own button.

        Only while floating, and that restriction is correctness rather
        than caution: a docked panel goes invisible whenever a neighbour
        is tabbed in front of it, and it has not been put away.
        """
        instance = instance_reference()
        if instance is None or instance.action is None:
            return
        container = instance.container
        if container is None or not container.isFloating():
            return
        if instance.action.isChecked() != visible:
            instance.action.setChecked(visible)

    def dispose(self):
        self._create_action = None
