"""The one list of panels the application can show.

Core panels and plugin panels register here alike, so a workspace window
never needs to know where a panel came from -- it asks the registry what
exists and its host builds what is asked for. The registry is application
scope and deliberately Qt-free: it is imported before any QApplication
exists.
"""

import logging


LOGGER = logging.getLogger(__name__)


class PanelRegistryError(Exception):
    """A panel could not be registered or found."""


class PanelRegistry:
    """Every panel the application knows, in registration order."""

    def __init__(self):
        self._descriptors = {}
        self._listeners = []

    def register(self, descriptor):
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

    def descriptor(self, panel_id):
        try:
            return self._descriptors[panel_id]
        except KeyError:
            raise PanelRegistryError(
                "Unknown panel {!r}.".format(panel_id)
            ) from None

    def descriptors(self, placement=None):
        return tuple(
            descriptor
            for descriptor in self._descriptors.values()
            if placement is None or descriptor.placement == placement
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
