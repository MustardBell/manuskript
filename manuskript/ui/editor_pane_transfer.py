"""Move one split Editor pane into a fresh Editor workspace."""

import logging

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from PyQt5.QtCore import QModelIndex, QPoint, QTimer
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QAction, QApplication

from manuskript.panels.core import EDITOR
from manuskript.services.workspace_state import PRIMARY
from manuskript.ui.workspace_surfaces import WorkspaceBuildIntent


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditorTabSnapshot:
    """Enough state to make a torn-off document view recognisably the same."""

    item_id: Optional[str]
    folder_view: str
    presentation_mode: Any
    cursor_position: int
    cursor_anchor: int
    scroll_value: int


@dataclass(frozen=True)
class EditorPaneTransferViews:
    """The window operations needed by one pane transfer."""

    menu: Any
    menu_anchor: Any
    object_parent: Any
    current_workspace: Any
    current_id: str
    host: Any
    tool_host: Any
    project_active: Callable[[], bool]
    flush_pending_edits: Callable[[], None]
    create_workspace: Callable[[WorkspaceBuildIntent], Any]
    close_workspace: Callable[[Any], None]
    place_workspace: Callable[[Any, Optional[QPoint]], None]
    show_status: Callable[[str, int, int], None]
    translate: Callable[[str], str]
    defer: Callable[[Callable[[], None]], None] = (
        lambda callback: QTimer.singleShot(0, callback)
    )

    @classmethod
    def for_window(cls, window, anchor=None):
        def place_workspace(workspace, position):
            if position is None:
                source = window.frameGeometry()
                position = source.topLeft() + QPoint(48, 48)
            available = QApplication.desktop().availableGeometry(workspace)
            frame = workspace.frameGeometry()
            x = max(
                available.left(),
                min(position.x() - 48, available.right() - frame.width() + 1),
            )
            y = max(
                available.top(),
                min(position.y() - 24, available.bottom() - frame.height() + 1),
            )
            workspace.move(x, y)

        return cls(
            menu=window.menuView,
            menu_anchor=anchor,
            object_parent=window,
            current_workspace=window,
            current_id=window.windowId,
            host=window.surfaceHost,
            tool_host=window.panelHost,
            project_active=lambda: window.projectRuntime.isOpen,
            flush_pending_edits=(
                window.projectLifecycleView.flush_pending_edits
            ),
            create_workspace=window.workspaceWindows.open_with_intent,
            close_workspace=lambda workspace: workspace.close(),
            place_workspace=place_workspace,
            show_status=window.statusPresenter.show,
            translate=window.tr,
        )


class EditorPaneTransferController:
    """Tear off a document pane without moving its whole Editor surface."""

    def __init__(self, views):
        self.views = views
        self._editor = None
        self.action = QAction(
            views.translate("Move Current Editor Pane to New Window"),
            views.object_parent,
        )
        self.action.setObjectName("actMoveEditorPaneToNewWindow")
        description = views.translate(
            "Move the active split pane and its open document tabs to a new "
            "Editor window"
        )
        self.action.setStatusTip(description)
        self.action.setToolTip(description)
        views.menu.insertAction(views.menu_anchor, self.action)
        self.action.triggered.connect(self.move_current_pane)
        views.menu.aboutToShow.connect(self.refresh_action)
        self.refresh_action()

    # WorkspaceSurfaceHost binding -------------------------------------

    def attach_surface(self, instance):
        if instance.id != EDITOR:
            return
        self._editor = instance.widget.editor
        self._editor.setPaneTearOffHandler(self.move_pane)
        self.refresh_action()

    def detach_surface(self, instance):
        if instance.id != EDITOR or self._editor is not instance.widget.editor:
            return
        self._editor.setPaneTearOffHandler(None)
        self._editor = None
        self.refresh_action()

    # Commands ----------------------------------------------------------

    def refresh_action(self):
        self.action.setEnabled(bool(
            self.views.project_active()
            and self._editor is not None
            and not self._editor.pluginWorkspaceActive
            and self._current_pane() is not None
        ))

    def move_current_pane(self, _checked=False):
        pane = self._current_pane()
        return self.move_pane(pane) if pane is not None else None

    def _current_pane(self):
        editor = self._editor
        if editor is None:
            return None
        current_tabs = editor.currentTabWidget()
        return next((
            pane
            for pane in editor.allTabSplitters()
            if pane.tab is current_tabs and pane.tab.count()
        ), None)

    def move_pane(self, pane, global_position=None):
        """Create the destination completely before removing source tabs."""

        editor = self._editor
        if (
            editor is None
            or editor.pluginWorkspaceActive
            or pane not in editor.allTabSplitters()
            or not pane.tab.count()
            or not self.views.project_active()
        ):
            return None

        snapshots = self._capture(pane)
        current = pane.tab.currentIndex()
        destination = None
        try:
            self.views.flush_pending_edits()
            destination = self.views.create_workspace(
                WorkspaceBuildIntent.for_new_surface(EDITOR)
            )
            destination_editor = destination.mainEditor
            destination_editor.closeAllTabs()
            created = self._restore(
                destination_editor,
                snapshots,
                current,
            )
            if len(created) != len(snapshots):
                raise RuntimeError(
                    "The destination did not restore every editor tab."
                )
        except Exception as error:
            LOGGER.exception("Could not move an Editor pane to a new window.")
            if destination is not None:
                self.views.close_workspace(destination)
            self.views.show_status(
                self.views.translate(
                    "The Editor pane could not be moved; it remains here: {}"
                ).format(error),
                8000,
                3,
            )
            return None

        # The destination is complete and bound to the shared project. Only
        # now may the source views be retired; any earlier failure left them
        # exactly where they were.
        original_count = pane.tab.count()
        for index in reversed(range(original_count)):
            pane.closeTab(index)

        self.views.place_workspace(destination, global_position)
        destination.show()
        destination.raise_()
        destination.activateWindow()

        if self._source_became_empty_wrapper():
            # The gesture originated inside this native widget tree. Let its
            # event finish before closeEvent disposes that tree.
            close_workspace = self.views.close_workspace
            source_workspace = self.views.current_workspace
            self.views.defer(
                lambda: close_workspace(source_workspace)
            )
        self.refresh_action()
        return destination

    def _capture(self, pane) -> Tuple[EditorTabSnapshot, ...]:
        result = []
        for index in range(pane.tab.count()):
            tab = pane.tab.widget(index)
            cursor = tab.txtRedacText.textCursor()
            result.append(EditorTabSnapshot(
                item_id=(str(tab.currentID) if tab.currentID else None),
                folder_view=str(tab.folderView),
                presentation_mode=tab.markdownPresentation.mode,
                cursor_position=cursor.position(),
                cursor_anchor=cursor.anchor(),
                scroll_value=tab.txtRedacText.verticalScrollBar().value(),
            ))
        return tuple(result)

    def _restore(self, editor, snapshots, current):
        target = editor.tabSplitter.tab
        created = []
        model = editor.editor_context.outline_model
        for snapshot in snapshots:
            index = (
                model.getIndexByID(snapshot.item_id)
                if snapshot.item_id is not None
                else QModelIndex()
            )
            if snapshot.item_id is not None and (
                index is None or not index.isValid()
            ):
                raise KeyError(
                    "Unknown document {!r}.".format(snapshot.item_id)
                )
            editor.setCurrentModelIndex(
                index,
                newTab=True,
                tabWidget=target,
            )
            tab = target.currentWidget()
            if tab is None:
                raise RuntimeError("The Editor did not create a document tab.")
            tab.setFolderView(snapshot.folder_view)
            tab.markdownPresentation.set_mode(snapshot.presentation_mode)
            cursor = tab.txtRedacText.textCursor()
            cursor.setPosition(snapshot.cursor_anchor)
            cursor.setPosition(
                snapshot.cursor_position,
                QTextCursor.KeepAnchor,
            )
            tab.txtRedacText.setTextCursor(cursor)
            tab.txtRedacText.verticalScrollBar().setValue(
                snapshot.scroll_value
            )
            created.append(tab)
        if 0 <= current < target.count():
            target.setCurrentIndex(current)
        editor.tabChanged()
        return tuple(created)

    def _source_became_empty_wrapper(self):
        return bool(
            self.views.current_id != PRIMARY
            and set(self.views.host.instances) == {EDITOR}
            and not self.views.tool_host.instances
            and self._editor is not None
            and not any(
                pane.tab.count()
                for pane in self._editor.allTabSplitters()
            )
        )

    def dispose(self):
        views = self.views
        if views is None:
            return
        if self._editor is not None:
            self._editor.setPaneTearOffHandler(None)
        try:
            views.menu.aboutToShow.disconnect(self.refresh_action)
        except (RuntimeError, TypeError):
            pass
        try:
            self.action.triggered.disconnect(self.move_current_pane)
        except (RuntimeError, TypeError):
            pass
        views.menu.removeAction(self.action)
        self.action.deleteLater()
        self._editor = None
        self.views = None
