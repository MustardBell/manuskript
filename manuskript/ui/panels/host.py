"""One window's panels, built from the shared registry.

Each workspace window owns one host. The host builds a panel's widget
from its descriptor, wraps it in whatever its placement calls for, and
keeps the living instance. It is the only code that knows how a panel is
mounted -- which is what makes moving an instance to another window a
change of host rather than a storm of signals.
"""

from dataclasses import dataclass
from functools import partial
from typing import Any, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAction,
    QDockWidget,
    QMessageBox,
    QSplitter,
    QWidget,
)

from manuskript.panels import DOCK, SPLITTER_SLOT, PanelDescriptor


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

    def __init__(self, window, registry):
        self.window = window
        self.registry = registry
        self._instances = {}

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
        if descriptor.placement == SPLITTER_SLOT:
            return self._open_splitter(descriptor, context)
        return self._open_dock(descriptor, context)

    def _open_splitter(self, descriptor, context):
        """Build a panel into the splitter slot its descriptor names."""
        window = self.window
        slot = descriptor.slot
        splitter = window.findChild(QSplitter, slot.splitter)
        try:
            if splitter is None:
                raise LookupError(
                    "This window has no splitter named {!r}.".format(
                        slot.splitter
                    )
                )
            widget = descriptor.widget_factory(context, splitter)
            if not isinstance(widget, QWidget):
                raise TypeError(
                    "Panel factories must return QWidget instances."
                )
        except Exception as error:
            QMessageBox.critical(
                window,
                window.tr("Panel failed"),
                "{}\n\n{}".format(descriptor.title, error),
            )
            return None
        splitter.insertWidget(slot.index, widget)
        instance = PanelInstance(
            descriptor=descriptor,
            widget=widget,
            action=self._toggle_action(descriptor, widget),
            host=self,
        )
        self._instances[descriptor.id] = instance
        return instance

    def _open_dock(self, descriptor, context):
        window = self.window
        dock = QDockWidget(descriptor.title, window)
        dock.setObjectName(
            descriptor.object_name or "panel.{}".format(descriptor.id)
        )
        dock.setAttribute(Qt.WA_DeleteOnClose, True)
        try:
            if descriptor.widget_factory is None:
                raise TypeError(
                    "Panel {} has no widget factory.".format(
                        descriptor.id
                    )
                )
            widget = descriptor.widget_factory(context, dock)
            if not isinstance(widget, QWidget):
                raise TypeError(
                    "Panel factories must return QWidget instances."
                )
        except Exception as error:
            dock.deleteLater()
            QMessageBox.critical(
                window,
                window.tr("Panel failed"),
                "{}\n\n{}".format(descriptor.title, error),
            )
            return None

        dock.setWidget(widget)
        dock.destroyed.connect(
            partial(self._container_destroyed, descriptor.id)
        )
        window.addDockWidget(Qt.RightDockWidgetArea, dock)
        instance = PanelInstance(
            descriptor=descriptor,
            widget=widget,
            container=dock,
            host=self,
        )
        self._instances[descriptor.id] = instance
        dock.show()
        return instance

    def _slot_splitter(self, descriptor):
        """The splitter a panel belongs in, if it belongs in one."""
        if descriptor.placement != SPLITTER_SLOT or descriptor.slot is None:
            return None
        return self.window.findChild(
            QSplitter, descriptor.slot.splitter,
        )

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

    def _toggle_action(self, descriptor, widget):
        """The one action controlling a panel's visibility.

        Everything that shows the panel -- toolbar buttons, menus, the
        search jump -- mirrors this action, so no two of them can
        disagree about what is on screen.
        """
        action = QAction(
            self.window.tr(descriptor.title),
            self.window,
        )
        action.setCheckable(True)
        action.setChecked(descriptor.default_visible)
        action.toggled.connect(widget.setVisible)
        widget.setVisible(descriptor.default_visible)
        return action

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
        if descriptor.placement == SPLITTER_SLOT:
            splitter = self._slot_splitter(descriptor)
            if splitter is None:
                raise LookupError(
                    "This window has no splitter named {!r}.".format(
                        descriptor.slot.splitter
                    )
                )
            splitter.insertWidget(descriptor.slot.index, widget)
        else:
            dock = QDockWidget(descriptor.title, self.window)
            dock.setObjectName(
                descriptor.object_name
                or "panel.{}".format(descriptor.id)
            )
            dock.setAttribute(Qt.WA_DeleteOnClose, True)
            dock.setWidget(widget)
            dock.destroyed.connect(
                partial(self._container_destroyed, descriptor.id)
            )
            self.window.addDockWidget(Qt.RightDockWidgetArea, dock)
            instance.container = dock
            dock.show()
        instance.action = self._toggle_action(descriptor, widget)
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
        dock = QDockWidget(self.window.tr(descriptor.title), self.window)
        dock.setObjectName(
            "panel.floating.{}".format(descriptor.id)
        )
        dock.setWidget(widget)
        dock.setFloating(True)
        instance.container = dock
        instance.action = self._toggle_action(descriptor, dock)
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
