"""Apply and capture one window's layout.

The window half of :mod:`manuskript.services.workspace_state`: it knows
which widgets hold what, and the store knows none of them. Each window
carries its own identifier, so two windows no longer save over each
other.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Tuple

from PyQt5.QtWidgets import QSplitter

from manuskript.panels import (
    SPLITTER_SLOT,
    PanelRegistryError,
    WorkspaceSurfaceDescriptor,
)
from manuskript.panels.core import EDITOR
from manuskript.services.workspace_state import (
    PRIMARY,
    WorkspaceStateStore,
    WorkspaceWindowState,
)
from manuskript.ui.legacy_layouts import legacy_docks_in
from manuskript.ui.editors.document_area_layout import (
    describe_area,
    restore_area,
)


@dataclass(frozen=True)
class WorkspaceStateViews:
    """Stable layout capabilities belonging to one workspace window."""

    restore_geometry: Callable[[Any], bool]
    restore_window_state: Callable[[Any], bool]
    #: Which docks this build no longer makes a saved layout still knows
    #: about. Given rather than called directly, because deciding whether
    #: an old arrangement may be applied is this controller's business
    #: while asking Qt about a payload is not.
    legacy_docks_in: Callable[[Any], Tuple[str, ...]]
    save_geometry: Callable[[], Any]
    save_window_state: Callable[[], Any]
    project_active: Callable[[], bool]
    project_docks: Tuple[Any, ...]
    default_dock_visibility: Mapping[str, bool]
    document_area: Callable[[], Any]
    #: The surface this window is showing, from the one owner that knows.
    #: It used to be the window's record of whatever last had semantic
    #: focus, which is a different fact and may name a tool panel -- so a
    #: window could file "project tree" as the surface it was showing.
    current_surface: Callable[[], str]
    select_surface: Callable[[str], bool]
    legacy_panel_for_tab: Callable[[Any], str]
    find_splitter: Callable[[str], Any]
    panel_registry: Any
    panel_host: Any
    #: The other owner. A surface is not shown or hidden and has no dock
    #: to arrange, so almost nothing here asks it anything -- but a
    #: surface may still declare state of its own, and a window that
    #: asked only the panel host would drop it without saying so.
    surface_host: Any

    @classmethod
    def for_window(cls, window):
        project_docks = (
            window.dckNavigation,
            window.dckCheatSheet,
            window.dckSearch,
        )
        def document_area():
            instance = window.surfaceHost.instance(EDITOR)
            return (
                instance.widget.editor.tabSplitter
                if instance is not None else None
            )

        return cls(
            restore_geometry=window.restoreGeometry,
            restore_window_state=window.restoreState,
            legacy_docks_in=legacy_docks_in,
            save_geometry=window.saveGeometry,
            save_window_state=window.saveState,
            project_active=lambda: window._projectSurfaceActive,
            project_docks=project_docks,
            default_dock_visibility=MappingProxyType({
                project_docks[0].objectName(): True,
                project_docks[1].objectName(): False,
                project_docks[2].objectName(): False,
            }),
            document_area=document_area,
            current_surface=lambda: window.surfaceHost.current() or "",
            select_surface=window.goToSurface,
            legacy_panel_for_tab=window.panelIdForLegacyTab,
            find_splitter=lambda name: window.findChild(QSplitter, name),
            panel_registry=window.panelRegistry,
            panel_host=window.panelHost,
            surface_host=window.surfaceHost,
        )


class WorkspaceStateController:
    """One window's layout, restored on open and captured on close."""

    def __init__(self, views, store=None, window_id=PRIMARY):
        self.views = views
        self.windowId = window_id
        self.store = (
            store if store is not None else WorkspaceStateStore()
        )
        self._dock_visibility = {}
        self._dock_visibility_locked = True
        #: Which version of the application wrote the layout restored
        #: here, so a window can tell an arrangement it chose from one
        #: an earlier version left behind.
        self.storedVersion = 0
        #: Whether a saved dock arrangement was applied to this window.
        #: False means there was none to apply or it named docks this
        #: build no longer makes, and the window has to place its own --
        #: asked here rather than at the call site, so one place decides
        #: what an old layout is worth.
        self.restoredLayout = False
        #: Which docks that layout still knew about, when it was refused.
        #: Kept because it says why, and because a surface a reader had
        #: torn out is a fact worth having when detaching into a real
        #: window lands.
        self._legacyDocks = ()
        #: What each project-scoped panel was showing before the welcome
        #: screen put it away, by panel id. Panels are hidden through the
        #: host rather than the widget, so their toggles keep agreeing
        #: with them, and the ids never mix with dock object names.
        self._projectPanelVisibility = {}
        #: This window's own view of the project -- which documents were
        #: open and which independently movable surface was active. Read at
        #: construction and
        #: applied when a project opens, since neither means anything
        #: until there is a project.
        self._documents = None
        self._activeSurface = None
        self._legacyMainTab = None
        #: Layout captured while a project was still open, for the parts
        #: of it that closing a project makes unknowable.
        self._remembered = {}

    @property
    def project_docks(self):
        return self.views.project_docks

    # --------------------------------------------------------- restore

    def restore(self):
        self.storedVersion = self.store.stored_version()
        state = self.store.load(self.windowId)
        if state.geometry is not None:
            self.views.restore_geometry(state.geometry)
        # Geometry is this window's size and place, and is still true
        # whoever wrote it. The arrangement of docks inside it is a
        # different matter: one written while the work surfaces were docks
        # names seven this build never makes, and Qt keeps the entry for a
        # dock it restored but never found -- handing it back on every
        # later save, for the life of the profile.
        #
        # So the layout is asked what it contains rather than what version
        # stamped it. A version number gets the one group of readers who
        # have layouts worth keeping exactly wrong: an installation coming
        # from upstream is stamped version one and names no surface docks
        # at all, because upstream's surfaces were pages.
        #
        # Refused whole when it does name them, since they cannot be taken
        # out -- measured, four ways, on Qt 5.15.3.
        self._legacyDocks = self.views.legacy_docks_in(state.window_state)
        self.restoredLayout = bool(
            state.window_state is not None
            and not self._legacyDocks
            and self.views.restore_window_state(state.window_state)
        )

        self._dock_visibility = (
            dict(state.docks)
            if state.docks
            else dict(self.views.default_dock_visibility)
        )
        self._dock_visibility_locked = True

        self._documents = state.documents
        self._activeSurface = self._surface_id(
            state.active_surface
            if state.active_surface
            else state.active_panel
        )
        self._legacyMainTab = state.main_tab
        self._restore_panel_state(state)
        for name, value in (state.splitters or {}).items():
            splitter = self.views.find_splitter(name)
            if splitter is not None and value is not None:
                splitter.restoreState(value)
        self._restore_panel_visibility(state)
        # The welcome screen is shown before any project opens and puts
        # the project panels away, so what they were restored to has to
        # be known by then -- otherwise opening a project brings back
        # nothing at all.
        self._remember_project_panels()
        return state

    def _restore_panel_state(self, state):
        stored = state.panel_state or {}
        for remembered, widget in self._remembered_panel_state():
            value = stored.get(remembered.key)
            if value is None:
                continue
            remembered.restore(widget, self._bool_list(value))

    def _restore_panel_visibility(self, state):
        host = self.views.panel_host
        # ``restoreState`` above has already arranged the docks, toggles
        # and all, so the toggles are told what it did before this
        # window's own record is applied on top.
        host.sync_visibility()
        for panel_id, visible in (state.panels or {}).items():
            if host.instance(panel_id) is not None:
                host.set_visible(panel_id, visible)

    # --------------------------------------------------------- capture

    def save(self):
        if self.views.project_active():
            self._remember_project_docks()
        remembered = self._remembered
        self.store.save(
            WorkspaceWindowState(
                geometry=self.views.save_geometry(),
                # Geometry is still true once a project closes; the dock
                # layout is not, because closing a project closes the
                # panels that were in it. So the arrangement recorded is
                # the one captured while they were still there.
                window_state=remembered.get(
                    "window_state", self.views.save_window_state(),
                ),
                splitters=self._splitter_state(),
                panels=remembered.get(
                    "panels", self._panel_visibility(),
                ),
                panel_state=self._panel_state(),
                docks=dict(self._dock_visibility),
                documents=self._open_documents(),
                active_surface=self._current_surface(),
            ),
            self.windowId,
        )

    def _open_documents(self):
        """Which documents this window has open, in its split layout.

        Only while a project is open: the welcome screen has no
        documents, and recording none then would tell the next launch to
        open nothing rather than to open what was there.
        """
        if not self.views.project_active():
            return self._documents
        area = self.views.document_area()
        return describe_area(area) if area is not None else self._documents

    def _current_surface(self):
        """Which work surface this window was showing."""
        if not self.views.project_active():
            return self._activeSurface
        return self.views.current_surface()

    def _surface_id(self, value):
        """Whatever this names, if it names a surface this build has.

        A layout written before the split filed semantic focus here, so
        it can say "project tree" -- a tool panel, which no navigator row
        stands for and which going to would mean nothing. It can also
        name a surface a plugin used to contribute. Either way the answer
        is that this window has nowhere recorded to return to.
        """
        surface_id = str(value or "")
        if not surface_id:
            return None
        try:
            descriptor = self.views.panel_registry.descriptor(surface_id)
        except PanelRegistryError:
            return None
        return (
            surface_id
            if isinstance(descriptor, WorkspaceSurfaceDescriptor)
            else None
        )

    def capture_view_state(self):
        """Remember this window's view of the project while it has one.

        Called as the project starts closing, because by the time the
        window's layout is saved the project is gone and the window is
        showing the welcome screen -- which is how the last window to
        close came to record nothing at all.
        """
        if not self.views.project_active():
            return
        area = self.views.document_area()
        if area is not None:
            self._documents = describe_area(area)
        self._activeSurface = self.views.current_surface()

    def capture_layout(self):
        """Remember the arrangement while every panel is still in it.

        Closing a project closes the panels that belonged to it, and
        QMainWindow.saveState only records the docks that exist when it
        runs -- so a layout saved after the close has forgotten exactly
        the panels whose places were worth keeping.
        """
        self.capture_view_state()
        if not self.views.project_active():
            return
        self._remembered["window_state"] = self.views.save_window_state()
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
        area = self.views.document_area()
        if recorded and area is not None:
            restore_area(
                area,
                recorded,
            )
        elif area is not None and documents and documents != [""]:
            area.restoreOpenIndexes(
                documents
            )
        surface_id = self._activeSurface
        if not surface_id:
            legacy_tab = (
                self._legacyMainTab
                if self._legacyMainTab is not None
                else main_tab
            )
            surface_id = self.views.legacy_panel_for_tab(legacy_tab)
        if surface_id:
            self.views.select_surface(surface_id)

    def _splitter_state(self):
        state = {}
        for name in self._splitter_names():
            splitter = self.views.find_splitter(name)
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
        registry = self.views.panel_registry
        names = []
        for descriptor in registry.descriptors(placement=SPLITTER_SLOT):
            slot = descriptor.slot
            if slot is not None and slot.splitter not in names:
                names.append(slot.splitter)
        return tuple(names)

    def _panel_visibility(self):
        host = self.views.panel_host
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
        """Everything in this window that remembers something, and what.

        The panels say what they keep; this only asks. The list used to be
        here, together with the widget methods to call and the widget to
        call them on, which made adding a panel with state of its own a
        change to this file and put one panel's internals in it.

        Both owners, because a surface may remember something too. Asking
        only the panel host would have dropped it silently, which is the
        one failure a person cannot report: nothing is wrong until the
        next launch, and then only a setting they chose is missing.
        """
        for host in (self.views.panel_host, self.views.surface_host):
            if host is None:
                continue
            for instance in host.instances.values():
                for remembered in instance.descriptor.state:
                    yield remembered, instance.widget

    # ----------------------------------------------- welcome screen

    def hide_project_docks(self):
        if not self._dock_visibility_locked:
            self._remember_project_docks()
        for dock in self.project_docks:
            dock.setVisible(False)
        host = self.views.panel_host
        for panel_id in self._project_panels():
            host.set_visible(panel_id, False)
        self._dock_visibility_locked = False

    def restore_project_docks(self):
        for dock in self.project_docks:
            dock.setVisible(
                self._dock_visibility.get(dock.objectName(), False)
            )
        host = self.views.panel_host
        for panel_id in self._project_panels():
            host.set_visible(
                panel_id, self._projectPanelVisibility.get(panel_id, False)
            )
        self._dock_visibility_locked = False

    def _project_panels(self):
        """The panels this window shows only while a project is open.

        A project panel used to sit in a splitter inside the project
        page, so the welcome screen hid it by covering it. A dock hangs
        off the window instead and stays up over the welcome screen
        unless it is put away explicitly.
        """
        host = self.views.panel_host
        if host is None:
            return ()
        return tuple(
            panel_id
            for panel_id, instance in host.instances.items()
            if instance.descriptor.requires_project
        )

    def _remember_project_docks(self):
        for dock in self.project_docks:
            self._dock_visibility[dock.objectName()] = dock.isVisible()
        self._remember_project_panels()

    def _remember_project_panels(self):
        host = self.views.panel_host
        for panel_id in self._project_panels():
            instance = host.instance(panel_id)
            shown = (
                instance.container
                if instance.container is not None
                else instance.widget
            )
            self._projectPanelVisibility[panel_id] = bool(
                shown is not None and not shown.isHidden()
            )

    @staticmethod
    def _bool_list(values):
        from manuskript.services.workspace_state import as_bool

        if isinstance(values, (list, tuple)):
            return [as_bool(value) for value in values]
        return values

    def dispose(self):
        """Release this controller's callbacks into its closing window."""
        self.views = None
