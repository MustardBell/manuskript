import logging
"""One window's panels: which of them it has, and where they are.

Each workspace window owns one host. It builds a panel's widget from its
descriptor, keeps the living instance, and hands the instance on when the
panel moves to another window -- which is what makes a move a change of
owner rather than a storm of signals.

What it no longer does itself, and each is one collaborator:

* :mod:`mounts` fastens a panel into the window, one class per way.
* :mod:`visibility` owns the toggle that shows and hides it, wherever it
  turned out to be mounted.
* :mod:`failures` says so when a panel could not be built.
* :mod:`directory` is where the application's other hosts are, so a panel
  that exists once can be found in whichever window has it.

What is left here is ownership: the instances, and the four moves a panel
can make -- opening, being released to another window, being torn off,
coming back.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any, Optional

from PyQt5.QtWidgets import QWidget

from manuskript.panels import DOCK, SPLITTER_SLOT, PanelDescriptor
from manuskript.ui.connections import weak_callback
from manuskript.ui.panels.mounts import mounts_for
from manuskript.ui.panels.visibility import PanelVisibility

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
    #: What this panel's dock calls when its visibility changes, kept so
    #: the connection can be taken back off again. A dock left connected
    #: to a panel that has gone still emits while Qt tears the window
    #: down, into a Python object that is no longer whole.
    container_watch: Optional[Any] = None


def _prepare_close(widget):
    """Let a panel wind down, without letting it stop the window closing.

    Optional by design: most panels are only widgets. One that has taken on
    something longer-lived says so by offering this, and a panel that raises
    on the way out is a plugin defect that must not become a window that
    cannot be closed.
    """

    prepare = getattr(widget, "prepare_close", None)
    if not callable(prepare):
        return
    try:
        prepare()
    except Exception:
        LOGGER.exception("A panel failed while preparing to close.")


class PanelHost:
    """Build, track and close the panels of a single window."""

    def __init__(self, views, registry, directory):
        self.views = views
        self.registry = registry
        # Where the application's other hosts are. Given rather than
        # reached for: it used to be a class attribute every host added
        # itself to, which is global state and is findable from anywhere
        # that can import this class.
        self.directory = directory
        self._instances = {}
        # One mount per way of fastening a panel, looked up by placement.
        # The host asks a mount to do it and never asks which kind it is.
        self._mounts = mounts_for(views)
        # What shows and hides a mounted panel, whichever thing it
        # turns out to be sitting in.
        self.visibility = PanelVisibility(views.create_action)
        # Where a panel that could not be built is reported.
        self.failures = views.failures
        #: Told about every panel this host mounts, whoever asked for it.
        #: The window offers a toggle for each; without this it could only
        #: offer them for the panels it opened itself, so a plugin's panel
        #: had no way into the toolbar every other panel is listed in.
        self.on_open = None
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
                self.views.activate_dock(existing.container)
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
            self.failures.report(descriptor, error, context)
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
        self.visibility.bind(instance)
        self._instances[descriptor.id] = instance
        # PanelVisibility.bind() has already applied default_visible to the
        # mounted thing. Showing every container here overruled that policy
        # while leaving its action unchecked: a supposedly hidden panel was
        # on screen and the first click on its toggle did nothing useful.
        if callable(self.on_open):
            self.on_open(instance)
        return instance

    def _watch_container(self, instance):
        """Forget a panel whose container Qt destroys under us."""
        container = instance.container
        if container is not None:
            container.destroyed.connect(
                weak_callback(partial(
                    self._container_destroyed,
                    instance.descriptor.id,
                ))
            )

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
        # Stop the toggle driving whatever it was driving -- the widget in
        # a slot, the dock when floating.
        self.visibility.unbind(instance)
        splitter = self._slot_splitter(instance.descriptor)
        if splitter is not None and splitter.indexOf(widget) >= 0:
            instance.slot_sizes = splitter.sizes()
        container = instance.container
        instance.container = None
        if container is not None:
            container.setWidget(None)
        if keep:
            self.views.park_widget(widget)
        else:
            # Going for good, so tell it. A panel may own work that
            # outlives its widget -- a thread reading Git, a request in
            # flight -- and dropping the widget silently leaves that work
            # holding something about to be freed. Transfer between windows
            # is not destruction and deliberately does not say this.
            _prepare_close(widget)
            widget.setParent(None)
        widget.hide()
        if container is not None:
            # Emptied and out of the layout, then left to die with the
            # window that owns it. Scheduling deletion instead would
            # leave it pending until an event loop runs, which in a
            # test there may never be.
            self.views.remove_dock(container)
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
        self.visibility.bind(instance)
        instance.host = self
        self._instances[descriptor.id] = instance
        # Through the toggle, which is what makes it visible: showing the
        # widget as well would only be a second way to say so, and every
        # extra show is a chance to take focus from somewhere.
        self.visibility.set_visible(instance)
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
        self.visibility.bind(instance)
        instance.host = self
        self._instances[descriptor.id] = instance
        widget.show()
        self.visibility.set_visible(instance)
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
        """Show or hide one of this window's panels, by name."""
        instance = self._instances.get(panel_id)
        if instance is not None:
            self.visibility.set_visible(instance, visible)

    def sync_visibility(self):
        """Make every toggle agree with where its panel actually is.

        A restored window state arranges docks directly, so the toggles
        have to be told what it did before anything trusts them.
        """
        for instance in self._instances.values():
            self.visibility.sync(instance)

    def reveal(self, panel_id):
        """Show a panel and bring its dock tab to the front."""

        instance = self._instances.get(panel_id)
        if instance is None:
            return False
        self.visibility.set_visible(instance, True)
        if instance.container is not None:
            self.views.activate_dock(instance.container)
        else:
            instance.widget.show()
            instance.widget.raise_()
        return True

    def close(self, panel_id):
        """Put a panel away. Its widget goes when nothing holds it."""
        self._detach(panel_id, keep=False)

    def close_all(self):
        for panel_id in tuple(self._instances):
            self.close(panel_id)

    def dispose(self):
        self.visibility.dispose()
        self.close_all()
        self.directory.remove(self)
        self._mounts.clear()
        self.views = None
        self.registry = None
        self.directory = None
        self.visibility = None
        self.failures = None

    def _container_destroyed(self, panel_id, _object=None):
        # Qt may destroy containers after the host is already being torn
        # down, so nothing here can assume attributes still exist.
        instances = getattr(self, "_instances", None)
        if instances is not None:
            instances.pop(panel_id, None)
