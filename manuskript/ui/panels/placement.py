"""Move and float panels without granting access to a whole window."""

from dataclasses import dataclass
from typing import Any, Callable
from weakref import ref, WeakMethod

from PyQt5.QtWidgets import QMenu


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


@dataclass(frozen=True)
class PanelPlacementViews:
    """Panel, menu, and peer-workspace capabilities for one workspace."""

    target: PanelPlacementTarget
    floating_menu: Any
    move_menu: Any
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

        target = PanelPlacementTarget(
            host=window.panelHost,
            toggles=toggles,
            title=title,
        )
        floating_menu = QMenu(window.tr("&Float Panel"), window)
        floating_menu.setObjectName("menuFloatPanel")
        move_menu = QMenu(window.tr("Move &Panel To"), window)
        move_menu.setObjectName("menuMovePanel")
        window.menuView.insertMenu(anchor, floating_menu)
        window.menuView.insertMenu(anchor, move_menu)
        window.menuView.insertSeparator(anchor)

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
            translate=translate,
            targets=targets,
        )


class PanelPlacementController:
    """Transfer and remount panels owned by one workspace."""

    def __init__(self, views):
        self.views = views
        self.target = views.target
        views.floating_menu.aboutToShow.connect(
            weak_slot(self.build_float_menu)
        )
        views.move_menu.aboutToShow.connect(
            weak_slot(self.build_move_menu)
        )

    @property
    def floating_menu(self):
        return self.views.floating_menu

    @property
    def move_menu(self):
        return self.views.move_menu

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
        for menu in (views.floating_menu, views.move_menu):
            try:
                menu.aboutToShow.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.target = None
        self.views = None
