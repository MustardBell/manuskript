"""One window's panels, built from the shared registry.

Each workspace window owns one host. The host builds a panel's widget
from its descriptor, wraps it in whatever its placement calls for, and
keeps the living instance. It is the only code that knows how a panel is
mounted -- which is what makes moving an instance to another window a
change of host rather than a storm of signals.
"""

import logging

from dataclasses import dataclass
from functools import partial
from typing import Any, Optional

from PyQt5.QtWidgets import QAction, QWidget

from manuskript.panels import DOCK, SPLITTER_SLOT, PanelDescriptor
from manuskript.ui.panels.mounts import mounts_for


LOGGER = logging.getLogger(__name__)


class PanelScopeError(Exception):
    """A panel was asked for in a way its declaration does not allow."""


@dataclass
class PanelInstance:
    """One living panel in one window.

    ``container`` is the mount -- a dock today, possibly nothing for a
    widget sitting directly in a splitter. ``action`` is the visibility
    toggle where the panel has one. The instance belongs to exactly one
    host at a time; transfer means release from one and adopt by another.
    """

    descriptor: PanelDescriptor
    widget: QWidget
    container: Optional[QWidget] = None
    action: Optional[Any] = None
    host: Optional["PanelHost"] = None
    #: The splitter's sizes while this panel was in it. Taking a widget
    #: out of a splitter lets Qt hand its space to the others, and
    #: putting it back takes that space from wherever Qt chooses -- so
    #: the arrangement is remembered and restored rather than recomputed.
    slot_sizes: Optional[list] = None


class PanelHost:
    """Build, track and close the panels of a single window."""

    def __init__(self, window, registry, directory):
        self.window = window
        self.registry = registry
        # Where the application's other hosts are. Given rather than
        # reached for: it used to be a class attribute every host added
        # itself to, which is global state and is findable from anywhere
        # that can import this class.
        self.directory = directory
        self._instances = {}
        # One mount per way of fastening a panel, looked up by placement.
        # The host asks a mount to do it and never asks which kind it is.
        self._mounts = mounts_for(window)
        directory.add(self)

    def instance(self, panel_id):
        return self._instances.get(panel_id)

    @property
    def instances(self):
        return dict(self._instances)

    def open(self, panel_id, context):
        """Show a panel, building it first if this window has none.

        Returns the instance, or None when the factory failed -- the
        failure is reported to the person, not raised at the caller,
        because a broken panel must not take the action that opened it
        down with it.
        """
        existing = self._instances.get(panel_id)
        if existing is not None:
            if existing.container is not None:
                existing.container.show()
                existing.container.raise_()
            return existing
        descriptor = self.registry.descriptor(panel_id)
        if not descriptor.per_window:
            # A singleton exists once in the application. Building a
            # second would give two windows two panels answering to one
            # identifier, which is the mistake that made opening a
            # second window fail before multiplicity was stated.
            held = self.directory.holder(panel_id, besides=self)
            if held is not None:
                raise PanelScopeError(
                    "Panel {} exists once in the application and is "
                    "already open in another window; move it rather "
                    "than opening another.".format(panel_id)
                )
        return self._build(descriptor, context)

    def _mount(self, descriptor):
        """How this panel is fastened, by what its descriptor declares."""
        try:
            return self._mounts[descriptor.placement]
        except KeyError:
            raise LookupError(
                "Panel {} asks to be mounted as {!r}, and this window "
                "has no way to do that.".format(
                    descriptor.id, descriptor.placement,
                )
            ) from None

    def _build(self, descriptor, context):
        """Build a panel and fasten it, whichever way it is fastened.

        One path for both placements. There were two, alike in every step
        but the mounting, so a change to what opening a panel means had to
        be made twice -- and the toggle a dock panel needs was for a while
        made in only one of them.
        """
        mount = None
        container = None
        try:
            # Inside the report, like everything else that can go wrong
            # here: a panel asking for a mounting this window has not got
            # is still a broken panel, not a reason to take down whatever
            # asked for it.
            mount = self._mount(descriptor)
            parent, container = mount.prepare(descriptor)
            if descriptor.widget_factory is None:
                raise TypeError(
                    "Panel {} has no widget factory.".format(descriptor.id)
                )
            widget = descriptor.widget_factory(context, parent)
            if not isinstance(widget, QWidget):
                raise TypeError(
                    "Panel factories must return QWidget instances."
                )
            mount.install(descriptor, widget, container)
        except Exception as error:
            if mount is not None:
                mount.discard(container)
            self._report_failure(descriptor, error, context)
            return None

        instance = PanelInstance(
            descriptor=descriptor,
            widget=widget,
            container=container,
            host=self,
        )
        self._watch_container(instance)
        # Every mounted panel gets a toggle, dock or slot, so set_visible
        # can reach it and so putting it away puts away whatever it is
        # actually sitting in.
        self._mount_action(instance)
        self._instances[descriptor.id] = instance
        if container is not None:
            container.show()
        return instance

    def _watch_container(self, instance):
        """Forget a panel whose container Qt destroys under us."""
        container = instance.container
        if container is not None:
            container.destroyed.connect(
                partial(self._container_destroyed, instance.descriptor.id)
            )

    def _report_failure(self, descriptor, error, context=None):
        """Say a panel could not be built, without blocking on it.

        This used to raise a modal dialog. A modal turns any factory
        fault into something that waits for a person, which in a test
        run is a hang rather than a failure -- the suite stopped at the
        same point twice and I mistook it for two runs competing.

        Told, not asked: the status bar carries it where the window has
        one, and the log always does, so a broken panel costs the person
        a line rather than their attention.
        """
        message = self.window.tr(
            "The {} panel could not be opened: {}"
        ).format(descriptor.title, error)
        LOGGER.warning(
            "Panel %s failed to build: %s", descriptor.id, error,
        )
        show_status = getattr(context, "show_status", None)
        if show_status is None:
            presenter = getattr(self.window, "statusPresenter", None)
            show_status = (
                presenter.show if presenter is not None else None
            )
        if show_status is not None:
            show_status(message, 8000, 2)

    def _slot_splitter(self, descriptor):
        """The splitter a panel belongs in, if it belongs in one."""
        return self._mounts[SPLITTER_SLOT].find(descriptor)

    @staticmethod
    def _restore_slot_sizes(splitter, instance):
        """Give the splitter back the arrangement it had.

        Without this, a panel that leaves and returns takes its space
        from whichever neighbour Qt picks -- which is how re-docking the
        metadata panel collapsed the editor beside it.
        """
        sizes = instance.slot_sizes
        instance.slot_sizes = None
        if sizes and len(sizes) == splitter.count():
            splitter.setSizes(sizes)

    @staticmethod
    def _shown_thing(instance):
        """What showing or hiding this panel means where it now sits.

        The dock when it has one, the widget otherwise. Asking the
        instance rather than the call site is the point: three places
        mount panels, and one of them used to answer "the widget" for a
        docked panel, so unchecking a moved panel emptied its dock and
        left the frame standing.
        """
        if instance.container is not None:
            return instance.container
        return instance.widget

    def _mount_action(self, instance):
        """Give a mounted panel the one action that shows and hides it.

        Everything that shows the panel -- toolbar buttons, menus, the
        search jump -- mirrors this action, so no two of them can
        disagree about what is on screen.
        """
        descriptor = instance.descriptor
        target = self._shown_thing(instance)
        action = QAction(
            self.window.tr(descriptor.title),
            self.window,
        )
        action.setCheckable(True)
        action.setChecked(descriptor.default_visible)
        action.toggled.connect(target.setVisible)
        target.setVisible(descriptor.default_visible)
        if instance.container is not None:
            instance.container.visibilityChanged.connect(
                partial(self._container_visibility_changed, descriptor.id)
            )
        instance.action = action
        return action

    def _container_visibility_changed(self, panel_id, visible):
        """Follow a floating dock the person closed with its own button.

        Only while floating, and that restriction is not caution but
        correctness: Qt hides a docked widget whenever another tab in the
        same area is selected, so treating every invisibility as "put
        away" would close a panel merely tabbed behind its neighbour. A
        floating dock is never tabbed, so there the signal means what it
        appears to mean.
        """
        instance = self._instances.get(panel_id)
        if instance is None or instance.action is None:
            return
        container = instance.container
        if container is None or not container.isFloating():
            return
        if instance.action.isChecked() != visible:
            instance.action.setChecked(visible)

    def release(self, panel_id):
        """Detach a living panel, leaving it whole.

        The widget keeps its state and its model connections -- those
        bind to the project runtime, not to a window, which is why a
        move costs a reparent rather than a rebuild. Only the couplings
        that are this window's are undone: the toggle action, and the
        mount it was sitting in.
        """
        return self._detach(panel_id, keep=True)

    def _detach(self, panel_id, keep):
        """Take a panel off this window, leaving its widget owned once.

        ``keep`` decides who owns the widget afterwards. Parked on the
        window when another host is about to adopt it; handed to Python
        when nobody is, so it is freed exactly when the last reference
        to it goes.

        Either way the widget leaves the container first. A dock with
        WA_DeleteOnClose deletes its child, and a surviving Python
        wrapper over a deleted widget crashes the interpreter later --
        during a garbage collection, with no stack that names this code.
        """
        instance = self._instances.pop(panel_id, None)
        if instance is None:
            return None
        widget = instance.widget
        widget.hide()
        if instance.action is not None:
            # Stop driving whatever it was driving -- the widget in a
            # slot, the dock when floating. The action belongs to the
            # window and goes with it; an adopting host makes its own.
            try:
                instance.action.toggled.disconnect()
            except TypeError:
                pass
            instance.action.setEnabled(False)
            instance.action = None
        splitter = self._slot_splitter(instance.descriptor)
        if splitter is not None and splitter.indexOf(widget) >= 0:
            instance.slot_sizes = splitter.sizes()
        container = instance.container
        instance.container = None
        if container is not None:
            container.setWidget(None)
        widget.setParent(self.window if keep else None)
        widget.hide()
        if container is not None:
            # Emptied and out of the layout, then left to die with the
            # window that owns it. Scheduling deletion instead would
            # leave it pending until an event loop runs, which in a
            # test there may never be.
            self.window.removeDockWidget(container)
        instance.host = None
        return instance

    def adopt(self, instance):
        """Take in a panel another host released.

        Mounted by its descriptor's placement, as though this window had
        built it, and given a fresh toggle of its own.
        """
        descriptor = instance.descriptor
        if descriptor.id in self._instances:
            raise ValueError(
                "This window already shows panel {}.".format(
                    descriptor.id
                )
            )
        widget = instance.widget
        mount = self._mount(descriptor)
        # A container it did not arrive with: the one it had belonged to
        # the window that let it go.
        _parent, container = mount.prepare(descriptor)
        mount.install(descriptor, widget, container)
        instance.container = container
        self._watch_container(instance)
        if container is not None:
            container.show()
        # After the container is set, so the toggle drives the dock a
        # moved panel now lives in rather than the widget inside it.
        self._mount_action(instance)
        instance.host = self
        self._instances[descriptor.id] = instance
        # Through the action, which is what makes it visible: showing the
        # widget as well would only be a second way to say so, and every
        # extra show is a chance to take focus from somewhere.
        instance.action.setChecked(True)
        # Only once it is visible. A hidden child of a splitter has no
        # width, so restoring the arrangement before this would hand the
        # returning panel nothing and leave the rest as Qt left them.
        splitter = self._slot_splitter(descriptor)
        if splitter is not None:
            self._restore_slot_sizes(splitter, instance)
        return instance

    def tear_off(self, panel_id):
        """Float a panel free of the layout, still owned by this window.

        A floating dock, not a window of its own: it never registers as
        a workspace, so it cannot keep a project open or answer for the
        last close. A splitter panel leaves its slot to do this, and
        re-docking puts it back.
        """
        instance = self._instances.get(panel_id)
        if instance is None:
            return None
        if instance.container is not None and instance.container.isFloating():
            return instance
        descriptor = instance.descriptor
        instance = self._detach(panel_id, keep=True)
        widget = instance.widget
        # A dock whatever the panel's placement: floating free is the one
        # thing every panel does the same way.
        mount = self._mounts[DOCK]
        _parent, dock = mount.prepare(descriptor)
        mount.install_floating(descriptor, widget, dock)
        instance.container = dock
        self._mount_action(instance)
        instance.host = self
        self._instances[descriptor.id] = instance
        widget.show()
        instance.action.setChecked(True)
        return instance

    def redock(self, panel_id):
        """Put a torn-off panel back where its descriptor says it goes."""
        instance = self._instances.get(panel_id)
        if instance is None:
            return None
        if instance.container is None or not instance.container.isFloating():
            return instance
        released = self.release(panel_id)
        return self.adopt(released)

    def floating(self):
        """Every panel of this window currently floating free."""
        return tuple(
            panel_id
            for panel_id, instance in self._instances.items()
            if instance.container is not None
            and instance.container.isFloating()
        )

    def set_visible(self, panel_id, visible=True):
        """Toggle a panel through its own action, wherever it is shown.

        Going through the action keeps every button that mirrors it in
        agreement, which poking the widget directly would not.
        """
        instance = self._instances.get(panel_id)
        if instance is not None and instance.action is not None:
            instance.action.setChecked(visible)

    def close(self, panel_id):
        """Put a panel away. Its widget goes when nothing holds it."""
        self._detach(panel_id, keep=False)

    def close_all(self):
        for panel_id in tuple(self._instances):
            self.close(panel_id)

    def _container_destroyed(self, panel_id, _object=None):
        # Qt may destroy containers after the host is already being torn
        # down, so nothing here can assume attributes still exist.
        instances = getattr(self, "_instances", None)
        if instances is not None:
            instances.pop(panel_id, None)
