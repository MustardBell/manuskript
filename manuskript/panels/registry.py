"""The one list of panels the application can show.

Core panels and plugin panels register here alike, so a workspace window
never needs to know where a panel came from -- it asks the registry what
exists and its host builds what is asked for. The registry is application
scope and deliberately Qt-free: it is imported before any QApplication
exists.
"""

import logging

from manuskript.panels.descriptor import (
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)


LOGGER = logging.getLogger(__name__)


class PanelRegistryError(Exception):
    """A panel could not be registered or found."""


class PanelRegistry:
    """Every panel the application knows, in registration order."""

    def __init__(self):
        self._descriptors = {}
        self._listeners = []

    def register(self, descriptor):
        if not isinstance(
            descriptor, (ToolPanelDescriptor, WorkspaceSurfaceDescriptor)
        ):
            # There are exactly two kinds, and anything else must not become
            # one by having an id. Accepting whatever had the right shape is
            # how a third thing would have quietly been filed as a tool
            # panel, since that used to mean "not a surface".
            raise PanelRegistryError(
                "{!r} is neither a workspace surface nor a tool panel."
                .format(descriptor)
            )
        if descriptor.id in self._descriptors:
            raise PanelRegistryError(
                "Panel ID {!r} is already registered.".format(
                    descriptor.id
                )
            )
        self._descriptors[descriptor.id] = descriptor
        self._notify()

    def deregister(self, panel_id):
        if panel_id not in self._descriptors:
            raise PanelRegistryError(
                "Unknown panel {!r}.".format(panel_id)
            )
        del self._descriptors[panel_id]
        self._notify()

    def __contains__(self, panel_id):
        return panel_id in self._descriptors

    def descriptor(self, panel_id):
        try:
            return self._descriptors[panel_id]
        except KeyError:
            raise PanelRegistryError(
                "Unknown panel {!r}.".format(panel_id)
            ) from None

    def descriptors(self, placement=None):
        """Everything registered, or the tool panels with one placement.

        Filtering by placement is a tool panel's question: a surface has no
        placement, so asking for one can only ever mean the docks and
        splitter slots.
        """

        if placement is None:
            return tuple(self._descriptors.values())
        return tuple(
            descriptor
            for descriptor in self.tool_panels()
            if descriptor.placement == placement
        )

    def surfaces(self):
        """The places the writer goes, in registration order.

        Asked separately from tool panels because almost nothing wants
        both: a navigator lists surfaces, a float menu offers tool panels,
        and code that had to filter one out of a mixed list was deciding
        which kind something was by looking at a field.
        """

        return tuple(
            descriptor
            for descriptor in self._descriptors.values()
            if isinstance(descriptor, WorkspaceSurfaceDescriptor)
        )

    def tool_panels(self):
        """The things kept beside what is being written.

        Tested positively. Defining a tool panel as "not a surface" would
        make anything unrecognised into one.
        """

        return tuple(
            descriptor
            for descriptor in self._descriptors.values()
            if isinstance(descriptor, ToolPanelDescriptor)
        )

    def subscribe(self, listener):
        """Call ``listener()`` after every change to what exists.

        Hosts use this to refresh their menus and toggles when a plugin
        arrives or leaves. Listeners get no arguments: the registry's
        contents are the message.
        """
        self._listeners.append(listener)

    def unsubscribe(self, listener):
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify(self):
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                # One host failing to refresh must not stop the change,
                # nor the other listeners from hearing about it.
                LOGGER.exception("A panel registry listener failed.")
