"""Remember tool-panel visibility per writing surface when declared."""

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

from PyQt5.QtCore import Qt


@dataclass(frozen=True)
class SurfacePanelRoute:
    panel_id: str
    default_surfaces: Tuple[str, ...]
    preferred_extent: int = 0


@dataclass(frozen=True)
class SurfacePanelRoutingViews:
    """Narrow window operations needed by surface-aware routing."""

    project_active: Callable[[], bool]
    routes: Callable[[], Tuple[SurfacePanelRoute, ...]]
    panel_visible: Callable[[str], bool]
    panel_extent: Callable[[str], int]
    set_panel_visible: Callable[[str, bool], None]
    remembered_visibility: Callable[[str], Optional[bool]]
    navigation_extent: Callable[[], int]
    restore_extents: Callable[[int, dict], None]

    @classmethod
    def for_window(cls, window):
        def routes():
            found = []
            for panel_id, instance in window.panelHost.instances.items():
                surfaces = instance.descriptor.visible_with_surfaces
                if surfaces is not None:
                    found.append(SurfacePanelRoute(
                        panel_id,
                        surfaces,
                        instance.descriptor.preferred_extent,
                    ))
            return tuple(found)

        def panel_visible(panel_id):
            instance = window.panelHost.instance(panel_id)
            if instance is None:
                return False
            shown = (
                instance.container
                if instance.container is not None else instance.widget
            )
            return shown is not None and not shown.isHidden()

        def dock_extent(dock):
            area = window.dockWidgetArea(dock)
            return (
                dock.height()
                if area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea)
                else dock.width()
            )

        def panel_extent(panel_id):
            instance = window.panelHost.instance(panel_id)
            if instance is None or instance.container is None:
                return 0
            return dock_extent(instance.container)

        def navigation_extent():
            if (
                not window.isVisible()
                and not window.windowState.restoredLayout
            ):
                return 200
            return window.dckNavigation.width()

        def restore_extents(navigation_width, panel_extents):
            # Hiding the only other dock in the left area makes Qt expand the
            # navigator to fill the vacated column. Showing it again then
            # divides that enlarged column proportionally. Preserve the
            # reader's navigator width and each arriving panel's last width
            # across the visibility operation.
            horizontal = [window.dckNavigation]
            horizontal_sizes = [max(1, int(navigation_width))]
            vertical = []
            vertical_sizes = []
            for panel_id, extent in panel_extents.items():
                instance = window.panelHost.instance(panel_id)
                dock = instance.container if instance is not None else None
                if dock is None or dock.isHidden() or not extent:
                    continue
                area = window.dockWidgetArea(dock)
                if area in (Qt.TopDockWidgetArea, Qt.BottomDockWidgetArea):
                    vertical.append(dock)
                    vertical_sizes.append(max(1, int(extent)))
                else:
                    horizontal.append(dock)
                    horizontal_sizes.append(max(1, int(extent)))
            # QMainWindow.resizeDocks preserves the combined extent of the
            # docks it is given. Passing only the navigator and a newly shown
            # project tree asks Qt to divide the old navigator column between
            # them; with the navigator's 200px minimum, the tree becomes the
            # unusably narrow remainder. Include the active work surface so
            # Qt can move the boundary between the tool column and the work
            # area while preserving the latter's generous width.
            active_id = window.surfaceHost.current()
            active = window.surfaceHost.instance(active_id)
            active_dock = active.container if active is not None else None
            if (
                active_dock is not None
                and not active_dock.isHidden()
                and active_dock not in horizontal
                and window.dockWidgetArea(active_dock) in (
                    Qt.LeftDockWidgetArea,
                    Qt.RightDockWidgetArea,
                )
            ):
                available_extent = sum(
                    max(1, candidate.width())
                    for candidate in horizontal
                ) + max(1, active_dock.width())
                horizontal.append(active_dock)
                horizontal_sizes.append(max(
                    1,
                    available_extent - sum(horizontal_sizes),
                ))
            window.resizeDocks(
                tuple(horizontal), tuple(horizontal_sizes), Qt.Horizontal,
            )
            if vertical:
                window.resizeDocks(
                    tuple(vertical), tuple(vertical_sizes), Qt.Vertical,
                )

        return cls(
            project_active=lambda: window._projectSurfaceActive,
            routes=routes,
            panel_visible=panel_visible,
            panel_extent=panel_extent,
            set_panel_visible=window.panelHost.set_visible,
            remembered_visibility=(
                window.windowState.remembered_panel_visibility
            ),
            navigation_extent=navigation_extent,
            restore_extents=restore_extents,
        )


class SurfacePanelRoutingController:
    """Apply declared defaults, then remember what the reader changes.

    Independent tool panels are never touched.  A routed panel starts from
    its declaration on a surface with no prior answer.  Before leaving that
    surface its actual visibility is remembered, so showing the project tree
    on General (or hiding it in Editor) remains the reader's choice when they
    return during this session.
    """

    def __init__(self, views):
        self.views = views
        self._current_surface = None
        self._applied = False
        self._visibility = {}
        self._extents = {}
        self._navigation_extent = 0
        self._visible_extents = {}

    def surface_changed(self, surface_id):
        surface_id = str(surface_id or "")
        if not surface_id:
            return
        previous = self._current_surface
        self._current_surface = surface_id
        if not self.views.project_active():
            return
        if self._applied and previous == surface_id:
            return
        routes = self.views.routes()
        navigation_extent = self.views.navigation_extent()
        if self._applied and previous:
            for route in routes:
                key = (previous, route.panel_id)
                visible = self.views.panel_visible(route.panel_id)
                self._visibility[key] = visible
                if visible:
                    self._extents[key] = self.views.panel_extent(
                        route.panel_id
                    )
        visible_extents = {}
        for route in routes:
            key = (surface_id, route.panel_id)
            if key in self._visibility:
                visible = self._visibility[key]
            elif not self._applied:
                remembered = self.views.remembered_visibility(route.panel_id)
                visible = (
                    remembered
                    if remembered is not None
                    else surface_id in route.default_surfaces
                )
            else:
                visible = surface_id in route.default_surfaces
            self.views.set_panel_visible(route.panel_id, visible)
            if visible:
                extent = self._extents.get(key, route.preferred_extent)
                if extent:
                    visible_extents[route.panel_id] = extent
        if routes:
            self.views.restore_extents(navigation_extent, visible_extents)
        self._navigation_extent = navigation_extent
        self._visible_extents = visible_extents
        self._applied = True

    def settle_layout(self):
        """Reapply defaults once a previously hidden window has geometry."""

        if self._applied and self.views.project_active():
            self.views.restore_extents(
                self._navigation_extent,
                dict(self._visible_extents),
            )

    def panel_opened(self, panel_id):
        """Route a contribution mounted after the current surface settled."""

        if not self._applied or not self.views.project_active():
            return
        route = next(
            (
                candidate for candidate in self.views.routes()
                if candidate.panel_id == panel_id
            ),
            None,
        )
        if route is None:
            return
        key = (self._current_surface, panel_id)
        if key in self._visibility:
            visible = self._visibility[key]
        else:
            remembered = self.views.remembered_visibility(panel_id)
            visible = (
                remembered
                if remembered is not None
                else self._current_surface in route.default_surfaces
            )
        self.views.set_panel_visible(panel_id, visible)
        if visible and route.preferred_extent:
            self._visible_extents[panel_id] = route.preferred_extent
        else:
            self._visible_extents.pop(panel_id, None)
        self.views.restore_extents(
            self._navigation_extent,
            dict(self._visible_extents),
        )

    def reset(self):
        """Forget per-session overrides before rebuilding first-open UI."""
        self._current_surface = None
        self._applied = False
        self._visibility.clear()
        self._extents.clear()
        self._navigation_extent = 0
        self._visible_extents.clear()

    def dispose(self):
        self.views = None
        self._visibility.clear()
        self._extents.clear()
        self._visible_extents.clear()
