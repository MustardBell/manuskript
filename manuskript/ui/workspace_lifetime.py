"""Deterministic teardown for one workspace's non-widget collaborators."""

import logging


LOGGER = logging.getLogger(__name__)


class WorkspaceLifetime:
    """Own disposable view-side collaborators in composition order.

    Qt owns the widget tree.  Python controllers and view ports are a
    separate object graph, often containing callbacks into that tree.  A
    workspace owns those collaborators explicitly and releases them in
    reverse construction order before Qt deletes its native objects.
    """

    def __init__(self):
        self._components = []

    def __len__(self):
        return len(self._components)

    def own(self, component):
        dispose = getattr(component, "dispose", None)
        if not callable(dispose):
            raise TypeError(
                "Workspace-owned components must provide dispose()."
            )
        self._components.append(component)
        return component

    def dispose(self):
        components = tuple(reversed(self._components))
        self._components.clear()
        for component in components:
            try:
                component.dispose()
            except Exception:
                # Closing a native widget tree must not stop halfway and
                # leave the remaining Python view ports attached to it.
                LOGGER.exception(
                    "Workspace component %s failed during disposal.",
                    type(component).__name__,
                )
