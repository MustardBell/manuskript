"""Presentation and lifecycle of one workspace's search dock."""

from dataclasses import dataclass
from typing import Any

from PyQt5.QtCore import QTimer


@dataclass(frozen=True)
class WorkspaceSearchViews:
    dock: Any
    query: Any

    @classmethod
    def for_window(cls, window):
        return cls(
            dock=window.dckSearch,
            query=window.widget.searchTextInput,
        )


class WorkspaceSearchController:
    """Reveal search and put the existing query under keyboard control."""

    def __init__(self, views):
        self._views = views

    def show(self, _checked=False):
        self._views.dock.show()
        self._views.dock.raise_()
        self._views.dock.activateWindow()
        # Qt defines a focus proxy for exactly this composite-widget case:
        # focusing the dock means focusing the line edit that handles its
        # keyboard input. This remains stable on Cocoa where a direct child
        # focus request during QAction dispatch may be rejected.
        self._views.dock.setFocusProxy(self._views.query)
        self._views.dock.setFocus()
        self._focus_query()
        # QAction restores the widget that owned focus after its triggered
        # handlers return on some Qt platform plugins. Reassert the user's
        # destination once that native action dispatch has settled.
        QTimer.singleShot(0, self._focus_query)

    def _focus_query(self):
        if self._views is None:
            return
        self._views.query.setFocus()
        self._views.query.selectAll()

    def dispose(self):
        self._views = None
