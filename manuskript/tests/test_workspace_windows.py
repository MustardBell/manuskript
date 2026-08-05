"""Two windows, one project.

This is what the runtime extraction was for. A second window is another
view: it edits the same models, shares the same undo history, and its
closing is not the project's closing. Each window keeps its own
selection, its own open documents and its own panels.
"""

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QPlainTextEdit

from manuskript.panels import PanelContext, PanelDescriptor
from manuskript.panels.core import METADATA, PROJECT_TREE
from manuskript.services.workspace_state import WorkspaceStateStore


def test_a_second_window_edits_the_same_project(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        # The project layer is shared, not copied.
        assert other.projectRuntime is window.projectRuntime
        assert other.projectManager is window.projectManager
        assert other.settingsManager is window.settingsManager
        assert other.undoStack is window.undoStack
        # And so are the models: editing in one window is editing the
        # project, which is the whole point.
        assert other.mdlOutline is window.mdlOutline
        assert other.mdlCharacter is window.mdlCharacter
        assert other.projectPluginData is window.projectPluginData
    finally:
        other.close()


def test_both_windows_are_workspaces_and_neither_is_last(
        MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        registry = window.windowRegistry
        assert set(registry.workspace_windows) >= {window, other}
        assert not registry.is_last(window)
        assert not registry.is_last(other)
    finally:
        other.close()


def test_the_project_reports_to_both_windows(MWEmptyProject):
    """Announcements reach every view, so both windows' widgets stay
    current when the project changes underneath them.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        views = window.projectRuntime.views.views
        assert window.projectLifecycleView in views
        assert other.projectLifecycleView in views
    finally:
        other.close()


def test_closing_the_second_window_leaves_the_project_open(
        MWEmptyProject):
    window = MWEmptyProject
    project = window.currentProject
    other = window.openWorkspaceWindow()

    other.close()

    assert window.projectRuntime.isOpen
    assert window.currentProject == project
    assert other.projectLifecycleView not in (
        window.projectRuntime.views.views
    )
    assert window.projectLifecycleView in (
        window.projectRuntime.views.views
    )
    assert other not in window.windowRegistry.workspace_windows
    # The first window is alone again, so its close is the project's.
    assert window.windowRegistry.is_last(window)


def test_each_window_has_its_own_panels(MWEmptyProject):
    """Panels are per window: one window hiding its metadata panel must
    not hide the other's.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        mine = window.panelHost.instance(METADATA)
        theirs = other.panelHost.instance(METADATA)
        assert mine is not theirs
        assert mine.widget is not theirs.widget
        assert mine.action is not theirs.action

        other.panelHost.set_visible(METADATA, True)
        window.panelHost.set_visible(METADATA, False)

        assert not theirs.widget.isHidden()
        assert mine.widget.isHidden()
    finally:
        other.close()


def test_each_window_has_its_own_tree_and_editor(MWEmptyProject):
    """Its own view of the outline, over the one shared model."""
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        assert other.treeRedacOutline is not window.treeRedacOutline
        assert other.mainEditor is not window.mainEditor
        assert (
            other.treeRedacOutline.model()
            is window.treeRedacOutline.model()
        )
        assert other.panelHost.instance(PROJECT_TREE).widget is (
            other.treeRedacWidget
        )
    finally:
        other.close()


def test_the_active_window_follows_focus(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        registry = window.windowRegistry
        registry.activate(other)
        assert registry.active is other
        registry.activate(window)
        assert registry.active is window
    finally:
        other.close()


# ------------------------------------------------- reopening a session

class isolated_session:
    """Give one window a private layout store.

    The main window is shared across the suite, so a test that records a
    session in the real store would have every later project-open reopen
    windows -- which is exactly what happened.
    """

    def __init__(self, window, tmp_path, open_windows=()):
        self.window = window
        self.path = str(tmp_path / "session.ini")
        self.open_windows = list(open_windows)
        self.previous = None
        self.opened = []

    def __enter__(self):
        controller = self.window.windowState
        self.previous = controller.store
        controller.store = WorkspaceStateStore(
            QSettings(self.path, QSettings.IniFormat)
        )
        controller.store.set_open_windows(self.open_windows)
        self.window._restoredWorkspaceWindows = False
        return self

    def restore(self):
        self.opened = list(self.window.restoreWorkspaceWindows())
        return self.opened

    def __exit__(self, *_exception):
        for entry in self.opened:
            entry.close()
        self.window.windowState.store = self.previous
        self.window._restoredWorkspaceWindows = True
        return False


def test_a_recorded_session_reopens_its_extra_windows(
        MWEmptyProject, tmp_path):
    """Opening a project brings back the windows the last session had,
    because a workspace window with no project is only a welcome screen.
    """
    window = MWEmptyProject
    with isolated_session(
        window, tmp_path, ["main", "window-restored"],
    ) as session:
        reopened = session.restore()

        assert [entry.windowId for entry in reopened] == [
            "window-restored",
        ]
        assert reopened[0].projectRuntime is window.projectRuntime
        assert reopened[0].currentProject == window.currentProject


def test_a_session_is_restored_once_per_window(
        MWEmptyProject, tmp_path):
    """project_opened fires whenever a project opens; reopening windows
    every time would multiply them.
    """
    window = MWEmptyProject
    with isolated_session(
        window, tmp_path, ["main", "window-restored"],
    ) as session:
        assert len(session.restore()) == 1
        assert window.restoreWorkspaceWindows() == ()


def test_a_window_already_open_is_not_opened_twice(
        MWEmptyProject, tmp_path):
    window = MWEmptyProject
    with isolated_session(window, tmp_path, ["main"]) as session:
        assert session.restore() == []
        assert window.openWorkspaceIds().count("main") == 1


def test_only_the_primary_window_restores_a_session(
        MWEmptyProject, tmp_path):
    """Otherwise each reopened window would reopen the session again."""
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with isolated_session(
            other, tmp_path, ["main", "window-unwanted"],
        ) as session:
            assert session.restore() == []
    finally:
        other.close()


def test_no_recorded_session_reopens_nothing(MWEmptyProject, tmp_path):
    window = MWEmptyProject
    with isolated_session(window, tmp_path, []) as session:
        assert session.restore() == []


def test_the_open_windows_are_what_a_quit_records(
        MWEmptyProject, tmp_path):
    """So the next launch comes back to the same set."""
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with isolated_session(window, tmp_path) as session:
            ids = window.openWorkspaceIds()
            assert other.windowId in ids

            window.windowState.store.set_open_windows(ids)

            assert set(
                window.windowState.store.open_windows()
            ) == set(ids)
            del session
    finally:
        other.close()


# --------------------------------------------- moving a panel between them

NOTES = "test.movable.notes"


class movable_panel:
    """A dock panel that only one window holds.

    Every window builds its own core panels, so those can never move
    into a window that already has one -- tearing them off is the move
    that makes sense for them. A plugin-style dock opened in one window
    is the case a move is for.
    """

    def __init__(self, window):
        self.window = window
        self.instance = None

    def __enter__(self):
        self.window.panelRegistry.register(PanelDescriptor(
            id=NOTES,
            title="Movable notes",
            widget_factory=lambda context, parent: QPlainTextEdit(parent),
        ))
        self.instance = self.window.panelHost.open(
            NOTES, PanelContext(window=self.window),
        )
        self.window.toolbar.addPanelToggle(
            self.instance.action,
            self.instance.widget,
            None,
            panel_id=NOTES,
        )
        return self.instance

    def __exit__(self, *_exception):
        for window in self.window.windowRegistry.workspace_windows:
            window.panelHost.close(NOTES)
            window.toolbar.removePanelToggle(NOTES)
        self.window.panelRegistry.deregister(NOTES)
        return False


def test_a_moved_panel_is_the_same_widget_in_the_other_window(
        MWEmptyProject):
    """Ownership transfer, not a rebuild: the widget itself crosses, so
    nothing it was showing is lost.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window) as panel:
            panel.widget.setPlainText("half-written note")
            original = panel.widget

            moved = window.movePanelTo(NOTES, other)

            assert moved.widget is original
            assert moved.widget.toPlainText() == "half-written note"
            assert moved.host is other.panelHost
            assert other.panelHost.instance(NOTES) is moved
            assert window.panelHost.instance(NOTES) is None
    finally:
        other.close()


def test_a_moved_panel_is_mounted_in_its_new_window(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window):
            moved = window.movePanelTo(NOTES, other)

            assert moved.container is not None
            assert other.dockWidgetArea(moved.container) == (
                Qt.RightDockWidgetArea
            )
            assert moved.widget.window() is other
    finally:
        other.close()


def test_a_moved_panel_is_toggled_from_its_new_window(MWEmptyProject):
    """Its old action died with the window it belonged to; the adopting
    host gives it one of its own.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window) as panel:
            old_action = panel.action

            moved = window.movePanelTo(NOTES, other)

            assert moved.action is not old_action
            assert moved.action.parent() is other

            moved.action.setChecked(False)
            assert moved.widget.isHidden()
            moved.action.setChecked(True)
            assert not moved.widget.isHidden()
    finally:
        other.close()


def test_the_toolbar_button_travels_with_the_panel(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window):
            assert NOTES in window.toolbar._panelToggles

            window.movePanelTo(NOTES, other)

            assert NOTES not in window.toolbar._panelToggles
            assert NOTES in other.toolbar._panelToggles
    finally:
        other.close()


def test_a_refused_move_leaves_the_panel_where_it_was(MWEmptyProject):
    """Releasing before the target could refuse would leave the panel
    belonging to nobody -- so the target is asked first.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        instance = window.panelHost.instance(METADATA)

        assert window.movePanelTo(METADATA, other) is None

        assert window.panelHost.instance(METADATA) is instance
        assert instance.widget is not None
        assert instance.action is not None
    finally:
        other.close()


def test_moving_a_panel_to_its_own_window_changes_nothing(
        MWEmptyProject):
    window = MWEmptyProject
    instance = window.panelHost.instance(METADATA)

    assert window.movePanelTo(METADATA, window) is instance
    assert window.panelHost.instance(METADATA) is instance


def test_the_move_menu_offers_only_panels_that_can_move(MWEmptyProject):
    """Core panels exist in every window, so they have nowhere to go."""
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window):
            window.buildPanelMoveMenu()

            titles = [
                action.menu().title()
                for action in window.menuMovePanel.actions()
                if action.menu() is not None
            ]
            assert titles == ["Movable notes"]
            targets = window.menuMovePanel.actions()[0].menu()
            assert len(targets.actions()) == 1
    finally:
        other.close()


def test_the_move_menu_says_when_nothing_can_move(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        window.buildPanelMoveMenu()

        entries = window.menuMovePanel.actions()
        assert len(entries) == 1
        assert "No panel can move" in entries[0].text()
        assert not entries[0].isEnabled()
    finally:
        other.close()


def test_the_move_menu_says_when_there_is_nowhere_to_move(
        MWEmptyProject):
    window = MWEmptyProject

    window.buildPanelMoveMenu()

    entries = window.menuMovePanel.actions()
    assert len(entries) == 1
    assert "No other window" in entries[0].text()
    assert not entries[0].isEnabled()
