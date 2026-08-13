"""Move, float, and deterministically arrange workspace panels.

Dragging remains available, but a precise layout must not depend on landing a
pointer inside Qt's ambiguous nested-dock target.  This controller exposes the
same operations as commands: move a dock to an edge, split it relative to a
visible neighbour, or tab the two together.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable
from weakref import ref, WeakKeyDictionary, WeakMethod

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QMenu


def weak_slot(method, *leading_args):
    """Connect Qt to a controller without making the signal own it."""
    method_ref = WeakMethod(method)

    def invoke(*signal_args):
        live_method = method_ref()
        if live_method is not None:
            return live_method(*leading_args, *signal_args)
        return None

    return invoke


def weak_target_slot(method, panel_id, target):
    """Resolve a destination only while its workspace still owns it."""
    method_ref = WeakMethod(method)
    target_ref = ref(target)

    def invoke(*signal_args):
        live_method = method_ref()
        live_target = target_ref()
        if live_method is not None and live_target is not None:
            return live_method(
                panel_id,
                live_target,
                *signal_args,
            )
        return None

    return invoke


def weak_dock_slot(method, dock):
    """Let a dock report its menu without either object owning the other."""
    method_ref = WeakMethod(method)
    dock_ref = ref(dock)

    def invoke(*signal_args):
        live_method = method_ref()
        live_dock = dock_ref()
        if live_method is not None and live_dock is not None:
            return live_method(live_dock, *signal_args)
        return None

    return invoke


@dataclass(frozen=True)
class PanelTogglePort:
    """The two toolbar operations that follow panel ownership."""

    remove: Callable[[str], None]
    add: Callable[..., None]

    @classmethod
    def for_toolbar(cls, toolbar):
        return cls(
            remove=toolbar.removePanelToggle,
            add=toolbar.addPanelToggle,
        )


@dataclass(frozen=True)
class PanelPlacementTarget:
    """What another workspace exposes when accepting a panel."""

    host: Any
    toggles: PanelTogglePort
    title: Callable[[], str]
    watch_dock: Callable[[Any], None]


@dataclass(frozen=True)
class DockEntry:
    """One dock that can participate in a window arrangement."""

    id: str
    title: str
    dock: Any


@dataclass(frozen=True)
class DockLayoutPort:
    """Only the QMainWindow capabilities needed to arrange docks."""

    entries: Callable[[], tuple]
    area: Callable[[Any], Any]
    add: Callable[[Any, Any], None]
    split: Callable[[Any, Any, Any], None]
    tabify: Callable[[Any, Any], None]


class DockRelation(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    ABOVE = "above"
    BELOW = "below"


@dataclass(frozen=True)
class PanelPlacementViews:
    """Panel, menu, and peer-workspace capabilities for one workspace."""

    target: PanelPlacementTarget
    floating_menu: Any
    move_menu: Any
    arrange_menu: Any
    docks: DockLayoutPort
    translate: Callable[[str], str]
    targets: Callable[[], tuple]

    @classmethod
    def for_window(cls, window, anchor=None):
        window_ref = ref(window)
        registry = window.windowRegistry
        toggles = PanelTogglePort.for_toolbar(window.toolbar)

        def title():
            owner = window_ref()
            return owner.windowTitle() if owner is not None else ""

        def translate(text):
            owner = window_ref()
            return owner.tr(text) if owner is not None else text

        def watch_dock(dock):
            owner = window_ref()
            controller = (
                getattr(owner, "panelPlacement", None)
                if owner is not None else None
            )
            if controller is not None:
                controller.watch_dock(dock)

        target = PanelPlacementTarget(
            host=window.panelHost,
            toggles=toggles,
            title=title,
            watch_dock=watch_dock,
        )
        floating_menu = QMenu(window.tr("&Float Panel"), window)
        floating_menu.setObjectName("menuFloatPanel")
        move_menu = QMenu(window.tr("Move &Panel To"), window)
        move_menu.setObjectName("menuMovePanel")
        arrange_menu = QMenu(window.tr("&Arrange Panel"), window)
        arrange_menu.setObjectName("menuArrangePanel")
        window.menuView.insertMenu(anchor, floating_menu)
        window.menuView.insertMenu(anchor, move_menu)
        window.menuView.insertMenu(anchor, arrange_menu)
        window.menuView.insertSeparator(anchor)

        def dock_entries():
            owner = window_ref()
            if owner is None:
                return ()
            return tuple(
                DockEntry(
                    id=dock.objectName() or "dock-{}".format(id(dock)),
                    title=dock.windowTitle() or dock.objectName(),
                    dock=dock,
                )
                for dock in owner.findChildren(
                    QDockWidget,
                    options=Qt.FindDirectChildrenOnly,
                )
            )

        docks = DockLayoutPort(
            entries=dock_entries,
            area=window.dockWidgetArea,
            add=window.addDockWidget,
            split=window.splitDockWidget,
            tabify=window.tabifyDockWidget,
        )

        def targets():
            return tuple(
                candidate.panelPlacement.target
                for candidate in registry.workspace_windows
                if hasattr(candidate, "panelPlacement")
                and candidate.panelPlacement.target is not target
            )

        return cls(
            target=target,
            floating_menu=floating_menu,
            move_menu=move_menu,
            arrange_menu=arrange_menu,
            docks=docks,
            translate=translate,
            targets=targets,
        )


class PanelPlacementController:
    """Transfer and remount panels owned by one workspace."""

    def __init__(self, views):
        self.views = views
        self.target = views.target
        self._dock_context_slots = WeakKeyDictionary()
        views.floating_menu.aboutToShow.connect(
            weak_slot(self.build_float_menu)
        )
        views.move_menu.aboutToShow.connect(
            weak_slot(self.build_move_menu)
        )
        views.arrange_menu.aboutToShow.connect(
            weak_slot(self.build_arrange_menu)
        )
        self.refresh_docks()

    @property
    def floating_menu(self):
        return self.views.floating_menu

    @property
    def move_menu(self):
        return self.views.move_menu

    @property
    def arrange_menu(self):
        return self.views.arrange_menu

    def move_to(self, panel_id, target, _checked=False):
        """Hand a living panel to a workspace that does not have it."""
        if isinstance(target, PanelPlacementController):
            target = target.target
        if target is self.target:
            return self.target.host.instance(panel_id)
        if target.host.instance(panel_id) is not None:
            # Refuse before release, or the panel would belong to nobody.
            return None
        instance = self.target.host.release(panel_id)
        if instance is None:
            return None
        try:
            adopted = target.host.adopt(instance)
        except Exception:
            # A mount can fail after release (for example, a plugin asks for
            # a placement the destination cannot provide).  Put the exact
            # living widget back instead of leaving it ownerless.
            restored = self.target.host.adopt(instance)
            self.target.toggles.remove(panel_id)
            self._add_toggle(self.target, restored)
            raise
        self.target.toggles.remove(panel_id)
        self._add_toggle(target, adopted)
        return adopted

    def toggle_floating(self, panel_id, _checked=False):
        """Float a docked panel, or return a floating panel to its slot."""
        host = self.target.host
        instance = host.instance(panel_id)
        if instance is None:
            return None
        if panel_id in host.floating():
            moved = host.redock(panel_id)
        else:
            moved = host.tear_off(panel_id)
        if moved is not None:
            self.target.toggles.remove(panel_id)
            self._add_toggle(self.target, moved)
        return moved

    @staticmethod
    def _add_toggle(target, instance):
        target.toggles.add(
            instance.action,
            instance.widget,
            instance.descriptor.group,
            panel_id=instance.descriptor.id,
        )
        target.watch_dock(instance.container)

    # ------------------------------------------------ local arrangement

    def refresh_docks(self):
        """Give every current dock the same title-bar context commands."""
        for entry in self.views.docks.entries():
            self.watch_dock(entry.dock)

    def watch_dock(self, dock):
        """Attach one context-menu route, including for late plugin docks."""
        if dock is None or dock in self._dock_context_slots:
            return
        slot = weak_dock_slot(self.show_dock_menu, dock)
        dock.setContextMenuPolicy(Qt.CustomContextMenu)
        dock.customContextMenuRequested.connect(slot)
        self._dock_context_slots[dock] = slot

    def _entries(self, visible_only=True):
        entries = self.views.docks.entries()
        if visible_only:
            entries = tuple(
                entry for entry in entries
                if not entry.dock.isHidden()
            )
        return tuple(sorted(
            entries,
            key=lambda entry: (entry.title.casefold(), entry.id),
        ))

    def _targets_for(self, source):
        return tuple(
            entry for entry in self._entries()
            if entry.dock is not source
            and not entry.dock.isFloating()
            and self.views.docks.area(entry.dock) != Qt.NoDockWidgetArea
        )

    def move_to_edge(self, dock, area, _checked=False):
        """Dock a panel at one of the window's four outer areas."""
        if dock is None:
            return False
        self.views.docks.add(area, dock)
        self._reveal_dock(dock)
        return True

    def _reveal_dock(self, dock):
        """Show a dock without letting a panel toggle disagree with it."""
        for instance in self.target.host.instances.values():
            if instance.container is dock:
                self.target.host.visibility.set_visible(instance, True)
                break
        else:
            dock.show()
        dock.raise_()

    def place_relative(self, dock, target, relation, _checked=False):
        """Place ``dock`` on an exact side of a docked neighbour."""
        if dock is None or target is None or dock is target:
            return False
        relation = DockRelation(relation)
        area = self.views.docks.area(target)
        if area == Qt.NoDockWidgetArea or target.isFloating():
            return False
        # A floating dock must first belong to the target's area. For a
        # dock already in the layout this also gives Qt one unambiguous
        # starting area before the split operation.
        self.views.docks.add(area, dock)
        if relation in (DockRelation.LEFT, DockRelation.ABOVE):
            first, second = dock, target
        else:
            first, second = target, dock
        orientation = (
            Qt.Horizontal
            if relation in (DockRelation.LEFT, DockRelation.RIGHT)
            else Qt.Vertical
        )
        self.views.docks.split(first, second, orientation)
        self._reveal_dock(dock)
        return True

    def tab_with(self, dock, target, _checked=False):
        """Put two docked panels in one tab group, selecting ``dock``."""
        if dock is None or target is None or dock is target:
            return False
        area = self.views.docks.area(target)
        if area == Qt.NoDockWidgetArea or target.isFloating():
            return False
        self.views.docks.add(area, dock)
        self.views.docks.tabify(target, dock)
        self._reveal_dock(dock)
        return True

    def _populate_arrangement(self, menu, dock):
        edge_menu = menu.addMenu(self.views.translate("Move to edge"))
        for label, area in (
            ("Left", Qt.LeftDockWidgetArea),
            ("Right", Qt.RightDockWidgetArea),
            ("Top", Qt.TopDockWidgetArea),
            ("Bottom", Qt.BottomDockWidgetArea),
        ):
            action = edge_menu.addAction(self.views.translate(label))
            action.setData(int(area))
            action.triggered.connect(
                weak_slot(self.move_to_edge, dock, area)
            )

        targets = self._targets_for(dock)
        menu.addSeparator()
        for label, relation in (
            ("Place left of", DockRelation.LEFT),
            ("Place right of", DockRelation.RIGHT),
            ("Place above", DockRelation.ABOVE),
            ("Place below", DockRelation.BELOW),
        ):
            submenu = menu.addMenu(self.views.translate(label))
            submenu.setEnabled(bool(targets))
            for target in targets:
                action = submenu.addAction(self.views.translate(target.title))
                action.setData(target.id)
                action.triggered.connect(
                    weak_slot(
                        self.place_relative,
                        dock,
                        target.dock,
                        relation,
                    )
                )
        tab_menu = menu.addMenu(self.views.translate("Tab with"))
        tab_menu.setEnabled(bool(targets))
        for target in targets:
            action = tab_menu.addAction(self.views.translate(target.title))
            action.setData(target.id)
            action.triggered.connect(
                weak_slot(self.tab_with, dock, target.dock)
            )

    def build_arrange_menu(self):
        """Offer deterministic placement for every visible current dock."""
        self.refresh_docks()
        menu = self.arrange_menu
        menu.clear()
        entries = self._entries()
        for entry in entries:
            submenu = menu.addMenu(self.views.translate(entry.title))
            submenu.menuAction().setData(entry.id)
            self._populate_arrangement(submenu, entry.dock)
        if not entries:
            action = menu.addAction(self.views.translate("No visible panel"))
            action.setEnabled(False)

    def show_dock_menu(self, dock, position):
        """Show the same precise commands from a dock's own title area."""
        menu = QMenu(dock)
        self._populate_arrangement(menu, dock)
        menu.exec_(dock.mapToGlobal(position))
        menu.deleteLater()

    def build_float_menu(self):
        """Offer each owned panel as a float/re-dock toggle."""
        menu = self.floating_menu
        host = self.target.host
        menu.clear()
        floating = set(host.floating())
        for panel_id, instance in sorted(host.instances.items()):
            action = menu.addAction(
                self.views.translate(instance.descriptor.title)
            )
            action.setData(panel_id)
            action.setCheckable(True)
            action.setChecked(panel_id in floating)
            action.triggered.connect(
                weak_slot(self.toggle_floating, panel_id)
            )
        if not host.instances:
            action = menu.addAction(
                self.views.translate("No panel in this window")
            )
            action.setEnabled(False)

    def build_move_menu(self):
        """Offer owned panels only to workspaces able to accept them."""
        menu = self.move_menu
        menu.clear()
        peers = self.views.targets()
        offered = 0
        for panel_id, instance in sorted(
            self.target.host.instances.items()
        ):
            targets = [
                target
                for target in peers
                if target.host.instance(panel_id) is None
            ]
            if not targets:
                continue
            submenu = menu.addMenu(
                self.views.translate(instance.descriptor.title)
            )
            submenu.menuAction().setData(panel_id)
            offered += 1
            for target in targets:
                action = submenu.addAction(target.title())
                action.setData(panel_id)
                action.triggered.connect(
                    weak_target_slot(self.move_to, panel_id, target)
                )
        if not offered:
            action = menu.addAction(self.views.translate(
                "No panel can move to another window"
                if peers
                else "No other window open"
            ))
            action.setEnabled(False)

    def dispose(self):
        """Release child-widget wrappers before Qt destroys their window.

        PyQt can otherwise collect a Python cycle after C++ has already
        deleted the parent-owned menus.  At that point those wrappers are
        stale, and cyclic collection can crash in SIP instead of raising the
        usual deleted-object exception.
        """
        views = self.views
        if views is None:
            return
        for dock, slot in tuple(self._dock_context_slots.items()):
            try:
                dock.customContextMenuRequested.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._dock_context_slots.clear()
        for menu in (
            views.floating_menu,
            views.move_menu,
            views.arrange_menu,
        ):
            try:
                menu.aboutToShow.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.target = None
        self.views = None
