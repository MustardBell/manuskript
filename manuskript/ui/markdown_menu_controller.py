"""Main-menu presentation of the active Markdown editor's state."""

from dataclasses import dataclass
from typing import Any

from PyQt5.QtWidgets import QAction, QActionGroup

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationBinding,
    presentation_mode_key,
)


@dataclass(frozen=True)
class MarkdownMenuViews:
    menu: Any
    action_parent: Any

    @classmethod
    def for_window(cls, window):
        return cls(
            menu=window.menuMarkdownMode,
            action_parent=window,
        )


class MarkdownMenuController:
    """Synchronize the global menu with one workspace's active leaf."""

    def __init__(self, views):
        self.views = views
        self.actions = {}
        self._group = None
        self.binding = MarkdownPresentationBinding(
            set_enabled=views.menu.setEnabled,
            state_changed=self._state_changed,
            sync_mode=self.sync_mode,
            sync_allowed_modes=self.sync_allowed_modes,
        )
        views.menu.clear()
        views.menu.setEnabled(False)

    def _state_changed(self, state):
        if state is None:
            self._clear_actions()

    def attach(self, state):
        self.binding.attach(state)

    def set_mode(self, mode):
        self.binding.set_mode(mode)

    def sync_mode(self, mode):
        mode = presentation_mode_key(mode)
        action = self.actions.get(mode)
        if action is not None:
            action.setChecked(True)

    def sync_allowed_modes(self, modes):
        state = self.binding.state
        menu = self.views.menu
        self._clear_actions()
        self._group = QActionGroup(menu)
        self._group.setExclusive(True)
        for supplied in modes:
            mode = presentation_mode_key(supplied)
            action = QAction(
                state.label_for(mode),
                self.views.action_parent,
            )
            action.setCheckable(True)
            action.setActionGroup(self._group)
            action.triggered.connect(
                lambda _checked=False, selected=mode:
                self.set_mode(selected)
            )
            menu.addAction(action)
            self.actions[mode] = action
        if state is not None:
            self.sync_mode(state.mode)

    def _clear_actions(self):
        """Retire actions from the previous leaf or catalogue revision."""

        menu = self.views.menu
        for action in self.actions.values():
            try:
                action.triggered.disconnect()
            except (RuntimeError, TypeError):
                pass
            menu.removeAction(action)
            action.deleteLater()
        self.actions = {}
        if self._group is not None:
            self._group.deleteLater()
            self._group = None
        menu.clear()

    def dispose(self):
        self.binding.dispose()
        self.binding = None
        self._clear_actions()
        self.views = None
