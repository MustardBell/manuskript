"""Main-menu presentation of the active Markdown editor's state."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationBinding,
    MarkdownPresentationMode,
)


@dataclass(frozen=True)
class MarkdownMenuViews:
    menu: Any
    actions: Mapping[MarkdownPresentationMode, Any]

    @classmethod
    def for_window(cls, window):
        return cls(
            menu=window.menuMarkdownMode,
            actions=MappingProxyType({
                MarkdownPresentationMode.SOURCE:
                    window.actMarkdownSource,
                MarkdownPresentationMode.FORMATTED_SOURCE:
                    window.actMarkdownFormattedSource,
                MarkdownPresentationMode.LIVE_PREVIEW:
                    window.actMarkdownLivePreview,
                MarkdownPresentationMode.READING:
                    window.actMarkdownReading,
            }),
        )


class MarkdownMenuController:
    """Synchronize the global menu with one workspace's active leaf."""

    def __init__(self, views):
        self.views = views
        self.binding = MarkdownPresentationBinding(
            set_enabled=views.menu.setEnabled,
            state_changed=self._state_changed,
            sync_mode=self.sync_mode,
            sync_allowed_modes=self.sync_allowed_modes,
        )
        views.menu.setEnabled(False)

    @staticmethod
    def _state_changed(_state):
        return None

    def attach(self, state):
        self.binding.attach(state)

    def set_mode(self, mode):
        self.binding.set_mode(mode)

    def sync_mode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        self.views.actions[mode].setChecked(True)

    def sync_allowed_modes(self, modes):
        allowed = set(modes)
        for mode, action in self.views.actions.items():
            action.setEnabled(mode in allowed)

    def dispose(self):
        self.binding.dispose()
        self.binding = None
        self.views = None
