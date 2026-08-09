"""Geometry operations for child windows owned by one workspace."""

from dataclasses import dataclass
from typing import Callable

from PyQt5.QtCore import QPoint


@dataclass(frozen=True)
class WindowPlacementViews:
    workspace_geometry: Callable[[], object]

    @classmethod
    def for_window(cls, window):
        return cls(workspace_geometry=window.geometry)


class WindowPlacementController:
    def __init__(self, views):
        self._views = views

    def center(self, child):
        child_geometry = child.geometry()
        workspace_geometry = self._views.workspace_geometry()
        child.move(
            workspace_geometry.center()
            - QPoint(
                int(child_geometry.width() / 2),
                int(child_geometry.height() / 2),
            )
        )

    def dispose(self):
        self._views = None
