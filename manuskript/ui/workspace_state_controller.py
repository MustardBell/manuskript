"""Apply and capture one window's layout.

The window half of :mod:`manuskript.services.workspace_state`: it knows
which widgets hold what, and the store knows none of them. Each window
carries its own identifier, so two windows no longer save over each
other.
"""

from PyQt5.QtWidgets import QSplitter

from manuskript.panels import SPLITTER_SLOT
from manuskript.services.workspace_state import (
    PRIMARY,
    WorkspaceStateStore,
    WorkspaceWindowState,
)
from manuskript.ui.editors.document_area_layout import (
    describe_area,
    restore_area,
)


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
        #: This window's own view of the project -- which documents were
        #: open and which main tab it was on. Read at construction and
        #: applied when a project opens, since neither means anything
        #: until there is a project.
        self._documents = None
        self._mainTab = None
        #: Layout captured while a project was still open, for the parts
        #: of it that closing a project makes unknowable.
        self._remembered = {}

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
        self._mainTab = state.main_tab
        self._restore_panel_state(state)
        for name, value in (state.splitters or {}).items():
            splitter = window.findChild(QSplitter, name)
            if splitter is not None and value is not None:
                splitter.restoreState(value)
        self._restore_panel_visibility(state)

    def _restore_panel_state(self, state):
        stored = state.panel_state or {}
        for remembered, widget in self._remembered_panel_state():
            value = stored.get(remembered.key)
            if value is None:
                continue
            remembered.restore(widget, self._bool_list(value))

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
        remembered = self._remembered
        self.store.save(
            WorkspaceWindowState(
                geometry=window.saveGeometry(),
                # Geometry is still true once a project closes; the dock
                # layout is not, because closing a project closes the
                # panels that were in it. So the arrangement recorded is
                # the one captured while they were still there.
                window_state=remembered.get(
                    "window_state", window.saveState(),
                ),
                splitters=self._splitter_state(),
                panels=remembered.get(
                    "panels", self._panel_visibility(),
                ),
                panel_state=self._panel_state(),
                docks=dict(self._dock_visibility),
                documents=self._open_documents(),
                main_tab=self._current_main_tab(),
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
        return describe_area(editor.tabSplitter)

    def _current_main_tab(self):
        """Which main tab this window is on, while it has a project."""
        if self.window.stack.currentIndex() != 1:
            return self._mainTab
        return self.window.tabMain.currentIndex()

    def capture_view_state(self):
        """Remember this window's view of the project while it has one.

        Called as the project starts closing, because by the time the
        window's layout is saved the project is gone and the window is
        showing the welcome screen -- which is how the last window to
        close came to record nothing at all.
        """
        if self.window.stack.currentIndex() != 1:
            return
        editor = getattr(self.window, "mainEditor", None)
        if editor is not None:
            self._documents = describe_area(editor.tabSplitter)
        self._mainTab = self.window.tabMain.currentIndex()

    def capture_layout(self):
        """Remember the arrangement while every panel is still in it.

        Closing a project closes the panels that belonged to it, and
        QMainWindow.saveState only records the docks that exist when it
        runs -- so a layout saved after the close has forgotten exactly
        the panels whose places were worth keeping.
        """
        self.capture_view_state()
        if self.window.stack.currentIndex() != 1:
            return
        self._remembered["window_state"] = self.window.saveState()
        self._remembered["panels"] = self._panel_visibility()

    def forget_captured_layout(self):
        """Take the live arrangement as the truth again.

        Once a project is open the window's own state is current, so a
        remembered one from the last close would be stale.
        """
        self._remembered.clear()

    def restore_view_state(self, documents=None, main_tab=None):
        """Put this window back the way it left the project.

        One path for both facts, because they are one thing: this
        window's own view of the project. Whatever this window never
        recorded falls back to what the project remembers, which is what
        every window did before views were per window, and is what
        somebody opening the file for the first time gets.
        """
        recorded = self._documents
        if recorded:
            restore_area(
                self.window.mainEditor.tabSplitter,
                recorded,
            )
        elif documents and documents != [""]:
            self.window.mainEditor.tabSplitter.restoreOpenIndexes(
                documents
            )
        tab = self._mainTab if self._mainTab is not None else main_tab
        if tab is not None:
            self.window.tabMain.setCurrentIndex(int(tab))

    def _splitter_state(self):
        state = {}
        for name in self._splitter_names():
            splitter = self.window.findChild(QSplitter, name)
            if splitter is not None:
                state[name] = splitter.saveState()
        return state

    def _splitter_names(self):
        """The splitters worth remembering: the ones panels sit in.

        Asked of the panels rather than listed here. A pair of names was
        hardcoded, so a panel put into a third splitter had its sizes
        forgotten until somebody thought to come and add it -- and the
        splitter holding the book summary was exactly that case.
        """
        registry = getattr(self.window, "panelRegistry", None)
        if registry is None:
            return ()
        names = []
        for descriptor in registry.descriptors(placement=SPLITTER_SLOT):
            slot = descriptor.slot
            if slot is not None and slot.splitter not in names:
                names.append(slot.splitter)
        return tuple(names)

    def _panel_visibility(self):
        host = getattr(self.window, "panelHost", None)
        if host is None:
            return {}
        return {
            panel_id: not instance.widget.isHidden()
            for panel_id, instance in host.instances.items()
        }

    def _panel_state(self):
        return {
            remembered.key: remembered.capture(widget)
            for remembered, widget in self._remembered_panel_state()
        }

    def _remembered_panel_state(self):
        """Every panel in this window that remembers something, and what.

        The panels say what they keep; this only asks. The list used to be
        here, together with the widget methods to call and the widget to
        call them on, which made adding a panel with state of its own a
        change to this file and put one panel's internals in it.
        """
        host = getattr(self.window, "panelHost", None)
        if host is None:
            return
        for instance in host.instances.values():
            for remembered in instance.descriptor.state:
                yield remembered, instance.widget

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
