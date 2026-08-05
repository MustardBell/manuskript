"""Apply and capture one window's layout.

The window half of :mod:`manuskript.services.workspace_state`: it knows
which widgets hold what, and the store knows none of them. Each window
carries its own identifier, so two windows no longer save over each
other.
"""

from PyQt5.QtWidgets import QSplitter

from manuskript.services.workspace_state import (
    PRIMARY,
    WorkspaceStateStore,
    WorkspaceWindowState,
)


#: Splitters whose sizes are worth remembering.
SPLITTERS = ("splitterRedacH", "splitterRedacV")

#: Panels that keep state of their own beyond being shown or hidden.
PANEL_STATE = {
    "core.metadata": (
        lambda panel: panel.saveState(),
        lambda panel, value: panel.restoreState(value),
    ),
    "core.metadata.revisions": (
        lambda panel: panel.revisions.saveState(),
        lambda panel, value: panel.revisions.restoreState(value),
    ),
}


class WorkspaceStateController:
    """One window's layout, restored on open and captured on close."""

    def __init__(self, window, store=None, window_id=PRIMARY):
        self.window = window
        self.windowId = window_id
        self.store = (
            store if store is not None else WorkspaceStateStore()
        )
        self._dock_visibility = {}
        self._dock_visibility_locked = True
        #: Read at construction and applied when a project opens, since
        #: there are no documents to reopen until there is a project.
        self._documents = None

    @property
    def project_docks(self):
        return (
            self.window.dckNavigation,
            self.window.dckCheatSheet,
            self.window.dckSearch,
        )

    # --------------------------------------------------------- restore

    def restore(self):
        state = self.store.load(self.windowId)
        window = self.window
        if state.geometry is not None:
            window.restoreGeometry(state.geometry)
        if state.window_state is not None:
            window.restoreState(state.window_state)

        self._dock_visibility = (
            dict(state.docks) if state.docks else {
                window.dckNavigation.objectName(): True,
                window.dckCheatSheet.objectName(): False,
                window.dckSearch.objectName(): False,
            }
        )
        self._dock_visibility_locked = True

        self._documents = state.documents
        self._restore_panel_state(state)
        for name, value in (state.splitters or {}).items():
            splitter = window.findChild(QSplitter, name)
            if splitter is not None and value is not None:
                splitter.restoreState(value)
        self._restore_panel_visibility(state)

    def _restore_panel_state(self, state):
        metadata = getattr(self.window, "redacMetadata", None)
        if metadata is None:
            return
        for key, (_save, load) in PANEL_STATE.items():
            value = (state.panel_state or {}).get(key)
            if value is None:
                continue
            load(metadata, self._bool_list(value))

    def _restore_panel_visibility(self, state):
        host = getattr(self.window, "panelHost", None)
        if host is None:
            return
        for panel_id, visible in (state.panels or {}).items():
            if host.instance(panel_id) is not None:
                host.set_visible(panel_id, visible)

    # --------------------------------------------------------- capture

    def save(self):
        window = self.window
        if window.stack.currentIndex() == 1:
            self._remember_project_docks()
        self.store.save(
            WorkspaceWindowState(
                geometry=window.saveGeometry(),
                window_state=window.saveState(),
                splitters=self._splitter_state(),
                panels=self._panel_visibility(),
                panel_state=self._panel_state(),
                docks=dict(self._dock_visibility),
                documents=self._open_documents(),
            ),
            self.windowId,
        )

    def _open_documents(self):
        """Which documents this window has open, in its split layout.

        Only while a project is open: the welcome screen has no
        documents, and recording none then would tell the next launch to
        open nothing rather than to open what was there.
        """
        if self.window.stack.currentIndex() != 1:
            return self._documents
        editor = getattr(self.window, "mainEditor", None)
        if editor is None:
            return self._documents
        return editor.tabSplitter.openIndexes()

    def capture_documents(self):
        """Remember this window's documents while it still has them.

        Called as the project starts closing, because by the time the
        window's layout is saved the project is gone and the window is
        showing the welcome screen -- which is how the last window to
        close came to record nothing at all.
        """
        editor = getattr(self.window, "mainEditor", None)
        if editor is not None and self.window.stack.currentIndex() == 1:
            self._documents = editor.tabSplitter.openIndexes()
        return self._documents

    def restore_documents(self):
        """Reopen this window's own documents, if it recorded any.

        Returns whether it did. A window with nothing recorded -- a new
        window, or one from before layouts were per window -- says so,
        and the caller falls back to what the project remembers.
        """
        documents = self._documents
        if not documents:
            return False
        self.window.mainEditor.tabSplitter.restoreOpenIndexes(documents)
        return True

    def _splitter_state(self):
        state = {}
        for name in SPLITTERS:
            splitter = self.window.findChild(QSplitter, name)
            if splitter is not None:
                state[name] = splitter.saveState()
        return state

    def _panel_visibility(self):
        host = getattr(self.window, "panelHost", None)
        if host is None:
            return {}
        return {
            panel_id: not instance.widget.isHidden()
            for panel_id, instance in host.instances.items()
        }

    def _panel_state(self):
        metadata = getattr(self.window, "redacMetadata", None)
        if metadata is None:
            return {}
        return {
            key: save(metadata)
            for key, (save, _load) in PANEL_STATE.items()
        }

    # ----------------------------------------------- welcome screen

    def hide_project_docks(self):
        if not self._dock_visibility_locked:
            self._remember_project_docks()
        for dock in self.project_docks:
            dock.setVisible(False)
        self._dock_visibility_locked = False

    def restore_project_docks(self):
        for dock in self.project_docks:
            dock.setVisible(
                self._dock_visibility.get(dock.objectName(), False)
            )
        self._dock_visibility_locked = False

    def _remember_project_docks(self):
        for dock in self.project_docks:
            self._dock_visibility[dock.objectName()] = dock.isVisible()

    @staticmethod
    def _bool_list(values):
        from manuskript.services.workspace_state import as_bool

        if isinstance(values, (list, tuple)):
            return [as_bool(value) for value in values]
        return values
