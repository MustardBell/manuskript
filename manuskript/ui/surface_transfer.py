"""Move a living workspace surface without rebuilding its view state."""

import logging

from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtCore import QEvent, QMimeData, QObject, QPoint, Qt
from PyQt5.QtGui import QColor, QDrag, QPalette
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QMenu,
    QVBoxLayout,
)

from manuskript.ui.workspace_surfaces import (
    WorkspaceBuildIntent,
    WorkspaceSurfaceError,
)
from manuskript.ui.tooltip_style import contrast_ratio


LOGGER = logging.getLogger(__name__)

SURFACE_MIME_TYPE = "application/x-manuskript-workspace-surface"


class NewWorkspaceDropTarget(QFrame):
    """An explicit destination: cancelling a desktop drag moves nothing."""

    def __init__(self, translate, parent=None):
        super().__init__(
            parent,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self._translate = translate
        self._surface_id = None
        self._dropped_surface_id = None
        self.setObjectName("newWorkspaceSurfaceDropTarget")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAccessibleName(translate("New workspace drop target"))
        self.setAccessibleDescription(translate(
            "Drop a writing surface here to move it to a new workspace "
            "window."
        ))

        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setMargin(14)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.label)

        palette = self.palette()
        self._background_color = palette.color(QPalette.Highlight)
        self._foreground_color = palette.color(QPalette.HighlightedText)
        if contrast_ratio(
            self._foreground_color, self._background_color,
        ) < 4.5:
            self._foreground_color = max(
                (QColor("black"), QColor("white")),
                key=lambda color: contrast_ratio(
                    color, self._background_color,
                ),
            )
        background = self._background_color.name()
        foreground = self._foreground_color.name()
        self.setStyleSheet(
            "QFrame#newWorkspaceSurfaceDropTarget {{"
            "background-color: {background}; color: {foreground};"
            "border: 2px solid {foreground}; border-radius: 4px;"
            "}} QFrame#newWorkspaceSurfaceDropTarget QLabel {{"
            "color: {foreground}; border: none; font-weight: bold;"
            "}}".format(
                background=background,
                foreground=foreground,
            )
        )
        self.setFixedWidth(320)

    def prepare(self, surface_id, title):
        self._surface_id = surface_id
        self._dropped_surface_id = None
        self.label.setText(self._translate(
            "Drop here to move\n{}\nto a new workspace window"
        ).format(title))
        self.adjustSize()
        self._place_beside_owner()

    def _place_beside_owner(self):
        owner = self.parentWidget()
        if owner is None:
            return
        owner_rect = owner.frameGeometry()
        available = QApplication.desktop().availableGeometry(owner)
        x = owner_rect.right() - self.width() - 24
        y = owner_rect.top() + 72
        x = max(available.left(), min(x, available.right() - self.width()))
        y = max(available.top(), min(y, available.bottom() - self.height()))
        self.move(x, y)

    def _offered_surface(self, mime_data):
        if not mime_data.hasFormat(SURFACE_MIME_TYPE):
            return None
        try:
            return bytes(mime_data.data(SURFACE_MIME_TYPE)).decode("utf-8")
        except (UnicodeError, ValueError):
            return None

    def dragEnterEvent(self, event):
        if self._offered_surface(event.mimeData()) == self._surface_id:
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        surface_id = self._offered_surface(event.mimeData())
        if surface_id != self._surface_id:
            event.ignore()
            return
        self._dropped_surface_id = surface_id
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def take_drop(self):
        surface_id = self._dropped_surface_id
        self._dropped_surface_id = None
        return surface_id


@dataclass(frozen=True)
class SurfaceTransferViews:
    """The narrow window operations needed by a surface move."""

    host: Any
    menu: Any
    object_parent: Any
    drag_source: Any
    surface_at_position: Callable[[Any], Any]
    drag_pixmap: Callable[[str], Any]
    translate: Callable[[str], str]
    project_active: Callable[[], bool]
    flush_pending_edits: Callable[[], None]
    create_workspace: Callable[[WorkspaceBuildIntent], Any]
    close_workspace: Callable[[Any], None]
    workspace_host: Callable[[Any], Any]
    show_status: Callable[[str, int, int], None]

    @classmethod
    def for_window(cls, window, anchor=None):
        menu = QMenu(
            window.tr("Move &Surface to New Window"), window,
        )
        menu.setObjectName("menuMoveSurfaceToNewWindow")
        menu.menuAction().setStatusTip(window.tr(
            "Move one writing surface, with its current view state, to a "
            "new workspace window"
        ))
        window.menuView.insertMenu(anchor, menu)

        def surface_at_position(position):
            item = window.lstTabs.itemAt(position)
            if item is None:
                return None
            target = window.navigator.target(window.lstTabs.row(item))
            if (
                target is None
                or not target.opens_panel
                or not window.surfaceHost.contains(target.panel_id)
            ):
                return None
            return target.panel_id

        def drag_pixmap(surface_id):
            row = window.navigator.row_for_panel(surface_id)
            item = window.lstTabs.item(row) if row is not None else None
            if item is None:
                return None
            rectangle = window.lstTabs.visualItemRect(item)
            return window.lstTabs.viewport().grab(rectangle)

        return cls(
            host=window.surfaceHost,
            menu=menu,
            object_parent=window,
            drag_source=window.lstTabs,
            surface_at_position=surface_at_position,
            drag_pixmap=drag_pixmap,
            translate=window.tr,
            project_active=lambda: window.projectRuntime.isOpen,
            flush_pending_edits=(
                window.projectLifecycleView.flush_pending_edits
            ),
            create_workspace=(
                window.workspaceWindows.open_with_intent
            ),
            close_workspace=lambda workspace: workspace.close(),
            workspace_host=lambda workspace: workspace.surfaceHost,
            show_status=window.statusPresenter.show,
        )


class SurfaceTransferController(QObject):
    """Transfer one surface to a workspace composed specifically for it."""

    def __init__(self, views):
        super().__init__(views.object_parent)
        self.views = views
        self._drag_start = None
        self._drag_surface_id = None
        self._drop_target = NewWorkspaceDropTarget(
            views.translate,
            views.object_parent,
        )
        self.views.menu.aboutToShow.connect(self.build_menu)
        self.views.drag_source.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is not self.views.drag_source:
            return False
        if event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and self._can_begin_drag():
                surface_id = self.views.surface_at_position(event.pos())
                if surface_id is not None:
                    self._drag_start = QPoint(event.pos())
                    self._drag_surface_id = surface_id
            return False
        if event.type() == QEvent.MouseButtonRelease:
            self._forget_drag()
            return False
        if event.type() != QEvent.MouseMove:
            return False
        if (
            self._drag_start is None
            or not event.buttons() & Qt.LeftButton
            or (
                event.pos() - self._drag_start
            ).manhattanLength() < QApplication.startDragDistance()
        ):
            return False

        surface_id = self._drag_surface_id
        self._forget_drag()
        self._drag_to_new_workspace(surface_id)
        return True

    def _can_begin_drag(self):
        return (
            self.views.project_active()
            and len(self.views.host.instances) > 1
        )

    def _forget_drag(self):
        self._drag_start = None
        self._drag_surface_id = None

    def _drag_to_new_workspace(self, surface_id):
        instance = self.views.host.instance(surface_id)
        if instance is None or not self._can_begin_drag():
            return None
        title = self.views.translate(instance.descriptor.title)
        self._drop_target.prepare(surface_id, title)
        self._drop_target.show()
        self._drop_target.raise_()

        drag = QDrag(self.views.drag_source)
        mime_data = QMimeData()
        mime_data.setData(SURFACE_MIME_TYPE, surface_id.encode("utf-8"))
        drag.setMimeData(mime_data)
        pixmap = self.views.drag_pixmap(surface_id)
        if pixmap is not None and not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())
        try:
            action = drag.exec_(Qt.MoveAction)
            dropped_surface = self._drop_target.take_drop()
        finally:
            self._drop_target.hide()
            drag.deleteLater()
        return self.complete_drag(surface_id, action, dropped_surface)

    def complete_drag(self, surface_id, action, dropped_surface):
        """Apply only an explicit drop; cancellation is always inert."""

        if action != Qt.MoveAction or dropped_surface != surface_id:
            return None
        return self.move_to_new_window(surface_id)

    def build_menu(self):
        menu = self.views.menu
        menu.clear()
        if not self.views.project_active():
            self._disabled_action("Open a project to move its surfaces")
            return

        instances = tuple(self.views.host.instances.values())
        if not instances:
            self._disabled_action("This workspace has no surface to move")
            return

        can_move = len(instances) > 1
        for instance in sorted(instances, key=self._sort_key):
            title = self.views.translate(instance.descriptor.title)
            action = menu.addAction(title.replace("&", "&&"))
            action.setData(instance.id)
            if can_move:
                action.setStatusTip(self.views.translate(
                    "Move {} to a new workspace window"
                ).format(title))
                action.triggered.connect(
                    lambda checked=False, surface_id=instance.id: (
                        self.move_to_new_window(surface_id, checked)
                    )
                )
            else:
                action.setEnabled(False)
                action.setStatusTip(self.views.translate(
                    "A workspace must keep at least one surface"
                ))

    @staticmethod
    def _sort_key(instance):
        navigator = instance.descriptor.navigator
        return (
            navigator.order if navigator is not None else 10_000,
            instance.descriptor.title.casefold(),
            instance.id,
        )

    def _disabled_action(self, text):
        action = self.views.menu.addAction(self.views.translate(text))
        action.setEnabled(False)
        return action

    def move_to_new_window(self, surface_id, _checked=False):
        """Move one living instance, or leave the source exactly usable."""

        views = self.views
        host = views.host
        instance = host.instance(surface_id)
        if instance is None or not views.project_active():
            return None
        if len(host.instances) <= 1:
            views.show_status(
                views.translate(
                    "A workspace must keep at least one surface."
                ),
                5000,
                2,
            )
            return None

        previous_surface = host.current()
        destination = None
        try:
            # Private editors are not represented by shared document
            # buffers. Submit them while their source bindings still exist.
            views.flush_pending_edits()
            detached = host.detach(surface_id)
            if detached is None:
                raise WorkspaceSurfaceError(
                    "The source no longer owns the requested surface."
                )
            instance = detached
            destination = views.create_workspace(
                WorkspaceBuildIntent.for_transfer(instance)
            )
            if destination is None:
                raise WorkspaceSurfaceError(
                    "The destination workspace was not created."
                )
            destination_host = views.workspace_host(destination)
            if instance.host is not destination_host:
                raise WorkspaceSurfaceError(
                    "The destination did not adopt the living surface."
                )
            return instance
        except Exception:
            LOGGER.exception(
                "Could not move workspace surface %s to a new window.",
                surface_id,
            )
            if destination is not None:
                try:
                    views.close_workspace(destination)
                except Exception:
                    LOGGER.exception(
                        "Could not close the failed surface destination."
                    )
            self._rollback(instance, previous_surface)
            views.show_status(
                views.translate(
                    "The surface could not be moved; it was restored to "
                    "this workspace."
                ),
                8000,
                3,
            )
            return None

    def _rollback(self, instance, previous_surface):
        """Recover an instance from either no owner or a partial owner."""

        host = self.views.host
        if instance is None:
            return
        owner = instance.host
        if owner is not None and owner is not host:
            owner.detach(instance.id)
        if instance.host is None:
            host.attach(instance)
        if previous_surface and host.contains(previous_surface):
            host.activate(previous_surface)

    def dispose(self):
        views = self.views
        if views is None:
            return
        try:
            views.menu.aboutToShow.disconnect(self.build_menu)
        except (RuntimeError, TypeError):
            pass
        views.drag_source.removeEventFilter(self)
        self._drop_target.hide()
        self._drop_target.deleteLater()
        self._drop_target = None
        views.menu.clear()
        self.views = None
