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

    def attach_existing(self, panel_id, widget):
        """Adopt a widget the window already built. Transitional.

        The panel gets its toggle action and its instance, but the
        widget stays wherever the Designer file put it. Factories
        replace this path one panel at a time; nothing new should
        use it.
        """
        descriptor = self.registry.descriptor(panel_id)
        instance = PanelInstance(
            descriptor=descriptor,
            widget=widget,
            action=self._toggle_action(descriptor, widget),
            host=self,
        )
        self._instances[panel_id] = instance
        return instance

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

    def set_visible(self, panel_id, visible=True):
        """Toggle a panel through its own action, wherever it is shown.

        Going through the action keeps every button that mirrors it in
        agreement, which poking the widget directly would not.
        """
        instance = self._instances.get(panel_id)
        if instance is not None and instance.action is not None:
            instance.action.setChecked(visible)

    def close(self, panel_id):
        instance = self._instances.pop(panel_id, None)
        if instance is not None and instance.container is not None:
            instance.container.close()

    def close_all(self):
        for panel_id in tuple(self._instances):
            self.close(panel_id)

    def _container_destroyed(self, panel_id, _object=None):
        # Qt may destroy containers after the host is already being torn
        # down, so nothing here can assume attributes still exist.
        instances = getattr(self, "_instances", None)
        if instances is not None:
            instances.pop(panel_id, None)
