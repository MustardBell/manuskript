"""Presentation and lifecycle of one workspace's search dock."""

from dataclasses import dataclass
from typing import Any


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
        self._views.dock.activateWindow()
        self._views.query.setFocus()
        self._views.query.selectAll()

    def dispose(self):
        self._views = None
