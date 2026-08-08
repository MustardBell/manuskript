"""Two windows, one project.

This is what the runtime extraction was for. A second window is another
view: it edits the same models, shares the same undo history, and its
closing is not the project's closing. Each window keeps its own
selection, its own open documents and its own panels.
"""

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QPlainTextEdit

import inspect

from manuskript.panels import PanelContext, PanelDescriptor
from manuskript.panels.core import METADATA, PROJECT_TREE, STORYLINE
from manuskript.services.workspace_state import WorkspaceStateStore
from manuskript.services.workspace_window_services import (
    WorkspaceWindowServices,
)


def test_a_window_is_given_its_services_rather_than_composing_them():
    """What a workspace window takes is the services object and its own id.

    It used to take ten separate optional services and build a fallback
    for every one it was not given, so a window handed nothing composed a
    second application -- its own panel registry, its own preferences, its
    own project -- and still looked like a view of the first. Nothing
    raised; the two windows simply were not looking at the same thing.
    """
    from manuskript.mainWindow import MainWindow

    parameters = list(
        inspect.signature(MainWindow.__init__).parameters
    )

    assert parameters == ["self", "services", "window_id"]


def test_a_second_window_shares_every_application_scope_service(
        MWEmptyProject):
    """Derived from the services themselves, so one added later is covered
    here without anyone remembering to add it.

    The failure this guards is silent: re-listing the services at the
    second construction site and missing one gave that window a fallback
    of its own instead of an error.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        assert other.services is window.services
        for name in WorkspaceWindowServices.field_names():
            shared = getattr(window.services, name)
            assert getattr(other.services, name) is shared
    finally:
        other.close()


def test_a_second_window_has_its_own_id_and_nothing_else_of_its_own(
        MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        assert other.windowId != window.windowId
        assert other.panelRegistry is window.panelRegistry
        assert other.windowRegistry is window.windowRegistry
        assert other.applicationPreferences is window.applicationPreferences
        assert other.mediaTypes is window.mediaTypes
        assert other.pluginContributions is window.pluginContributions
    finally:
        other.close()


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

        was_visible = not mine.widget.isHidden()
        other.panelHost.set_visible(METADATA, True)
        window.panelHost.set_visible(METADATA, False)

        assert not theirs.widget.isHidden()
        assert mine.widget.isHidden()
    finally:
        # The window is shared with every later test, so its panels are
        # left as they were found.
        window.panelHost.set_visible(METADATA, was_visible)
        other.close()


def test_each_window_has_its_own_tree_and_editor(MWEmptyProject):
    """Its own view of the outline, over the one shared model."""
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        other_tree = other.corePanels.project_tree.tree
        tree = window.corePanels.project_tree.tree
        assert other_tree is not tree
        assert other.mainEditor is not window.mainEditor
        assert other_tree.model() is tree.model()
        assert other.panelHost.instance(PROJECT_TREE).widget is (
            other.corePanels.project_tree.panel
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
            NOTES, PanelContext(translate=self.window.tr),
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
            # The dock goes away, not merely the widget inside it. The
            # old assertion was that the widget became hidden, which
            # passed precisely because the toggle emptied the frame and
            # left an empty dock standing in the new window.
            assert moved.container.isHidden()
            assert not moved.widget.isHidden()
            assert moved.container.widget() is moved.widget
            moved.action.setChecked(True)
            assert not moved.container.isHidden()
    finally:
        other.close()


def test_a_dock_panel_is_put_away_whole_wherever_it_was_mounted(
        MWEmptyProject):
    """One rule for every mount: a docked panel's toggle drives its dock.

    Three places mount panels -- opening, adopting a moved one, tearing
    one off -- and each used to decide for itself what the toggle drove.
    Opening gave a dock no toggle at all, adopting gave it one bound to
    the inner widget. So the same panel answered its own toggle
    differently depending on how it had arrived.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        with movable_panel(window) as panel:
            # As opened.
            assert panel.action is not None
            panel.action.setChecked(False)
            assert panel.container.isHidden()
            panel.action.setChecked(True)
            assert not panel.container.isHidden()

            # As adopted by another window.
            moved = window.movePanelTo(NOTES, other)
            moved.action.setChecked(False)
            assert moved.container.isHidden()
            moved.action.setChecked(True)

            # As torn off into a float.
            floated = other.panelHost.tear_off(NOTES)
            assert floated.container.isFloating()
            floated.action.setChecked(False)
            assert floated.container.isHidden()
            floated.action.setChecked(True)
            assert not floated.container.isHidden()
    finally:
        other.close()


def test_closing_a_floating_dock_unchecks_its_toggle(MWEmptyProject):
    """Qt closes a floating dock by its own button, without asking the
    host. The toggle has to notice, or it claims a panel is on screen
    that is not.
    """
    window = MWEmptyProject
    with movable_panel(window):
        floated = window.panelHost.tear_off(NOTES)
        assert floated.action.isChecked()

        floated.container.close()

        assert not floated.action.isChecked()


def test_a_docked_panel_tabbed_behind_another_stays_open(MWEmptyProject):
    """Qt hides a docked widget whenever a neighbour's tab is selected.
    Following that as though the person had closed the panel would put
    away whatever they tabbed away from.
    """
    window = MWEmptyProject
    with movable_panel(window) as panel:
        assert panel.action.isChecked()

        # What Qt does to the dock left behind when a tab is selected.
        panel.container.visibilityChanged.emit(False)

        assert panel.action.isChecked()
        assert not panel.container.isFloating()


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


# ------------------------------------------------- tearing a panel off

def test_a_torn_off_panel_floats_free_of_the_layout(MWEmptyProject):
    """A floating dock, keeping the same widget: the panel leaves the
    splitter without being rebuilt.
    """
    window = MWEmptyProject
    original = window.panelHost.instance(METADATA).widget
    try:
        floated = window.togglePanelFloating(METADATA)

        assert floated.widget is original
        assert floated.container is not None
        assert floated.container.isFloating()
        assert METADATA in window.panelHost.floating()
        assert window.splitterRedacH.indexOf(original) == -1
    finally:
        window.togglePanelFloating(METADATA)


def test_a_floating_panel_is_not_a_workspace_window(MWEmptyProject):
    """So it can neither keep a project open nor answer for the last
    close -- which a real second window would.
    """
    window = MWEmptyProject
    try:
        floated = window.togglePanelFloating(METADATA)

        assert floated.container not in (
            window.windowRegistry.workspace_windows
        )
        assert window.windowRegistry.is_last(window)
        assert len(window.windowRegistry.workspace_windows) == 1
    finally:
        window.togglePanelFloating(METADATA)


def test_redocking_returns_the_panel_to_its_slot(MWEmptyProject):
    """Its descriptor says where it belongs, so it goes back there
    rather than wherever it happened to come from.
    """
    window = MWEmptyProject
    original = window.panelHost.instance(METADATA).widget
    window.togglePanelFloating(METADATA)

    redocked = window.togglePanelFloating(METADATA)

    assert redocked.widget is original
    assert window.panelHost.floating() == ()
    assert window.splitterRedacH.indexOf(original) == 2
    assert redocked.container is None


def test_a_torn_off_panel_keeps_its_model_bindings(MWEmptyProject):
    """The binding is to the project's models, which belong to the
    runtime -- so floating the panel cannot break it.
    """
    window = MWEmptyProject
    panel = window.panelHost.instance(METADATA).widget
    before = panel.properties.txtTitle._model
    assert before is window.mdlOutline
    try:
        window.togglePanelFloating(METADATA)

        assert panel.properties.txtTitle._model is before
        assert panel.properties.txtGoal._model is window.mdlOutline
    finally:
        window.togglePanelFloating(METADATA)


def test_a_torn_off_panel_is_still_toggled_from_the_toolbar(
        MWEmptyProject):
    window = MWEmptyProject
    try:
        floated = window.togglePanelFloating(METADATA)

        assert METADATA in window.toolbar._panelToggles
        floated.action.setChecked(False)
        assert floated.container.isHidden()
        floated.action.setChecked(True)
        assert not floated.container.isHidden()
    finally:
        window.togglePanelFloating(METADATA)


def test_the_float_menu_marks_what_is_already_floating(MWEmptyProject):
    window = MWEmptyProject
    try:
        window.togglePanelFloating(METADATA)

        window.buildPanelFloatMenu()

        # By panel id, not by the text on the entry: the interface is
        # translated, and this test should not depend on the locale.
        checked = {
            action.data(): action.isChecked()
            for action in window.menuFloatPanel.actions()
        }
        assert checked[METADATA] is True
        assert checked[STORYLINE] is False
    finally:
        window.togglePanelFloating(METADATA)


def test_tearing_off_twice_is_not_two_floats(MWEmptyProject):
    window = MWEmptyProject
    try:
        first = window.panelHost.tear_off(METADATA)
        again = window.panelHost.tear_off(METADATA)

        assert again is first
        assert window.panelHost.floating() == (METADATA,)
    finally:
        window.panelHost.redock(METADATA)


def test_redocking_does_not_steal_space_from_the_editor(MWEmptyProject):
    """Taking a widget out of a splitter lets Qt hand its space to the
    others, and putting it back takes space from whichever neighbour Qt
    picks. That collapsed the editor beside the metadata panel.
    """
    window = MWEmptyProject
    # A hidden splitter child has no width, so the panel has to be
    # showing for its share to be the thing under test.
    was_visible = not window.panelHost.instance(METADATA).widget.isHidden()
    window.panelHost.set_visible(METADATA, True)
    splitter = window.splitterRedacH
    before = splitter.sizes()
    assert len(before) == 3

    window.togglePanelFloating(METADATA)
    assert len(splitter.sizes()) == 2
    window.togglePanelFloating(METADATA)

    # Exactly the arrangement it had, rather than whatever Qt would
    # redistribute -- the returning panel took its space from the editor
    # beside it and was itself left with none.
    assert splitter.sizes() == before
    assert splitter.sizes()[2] > 0

    window.panelHost.set_visible(METADATA, was_visible)


# ------------------------------------------- documents are per window

def test_each_window_records_its_own_open_documents(
        MWEmptyProject, tmp_path):
    """Two windows on one project are two places to be reading, so the
    project's single list of open documents is not enough to describe
    them.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        mine = WorkspaceStateStore(
            QSettings(str(tmp_path / "mine.ini"), QSettings.IniFormat)
        )
        theirs = WorkspaceStateStore(
            QSettings(str(tmp_path / "theirs.ini"), QSettings.IniFormat)
        )
        window.windowState.store = mine
        other.windowState.store = theirs

        window.windowState.save()
        other.windowState.save()

        # Each recorded something of its own, rather than one list
        # standing for both.
        assert mine.load(window.windowId).documents is not None
        assert theirs.load(other.windowId).documents is not None
    finally:
        other.close()


def test_a_window_with_no_recorded_documents_uses_the_projects(
        MWEmptyProject):
    """Which is what every window did before layouts were per window,
    so an existing project still opens where its author left it.
    """
    window = MWEmptyProject
    controller = window.windowState
    previous = controller._documents
    try:
        controller._documents = None

        # Nothing recorded, so the project's list is what applies.
        controller.restore_view_state(documents=[0, [], None], main_tab=0)
    finally:
        controller._documents = previous


def test_a_window_that_recorded_nothing_open_opens_nothing(
        MWEmptyProject):
    """Having recorded an empty layout is a fact about that window, not
    an absence of information -- so it is honoured rather than replaced
    by the project's list.
    """
    window = MWEmptyProject
    controller = window.windowState
    previous = controller._documents
    try:
        controller._documents = [0, [], None]

        controller.restore_view_state()
    finally:
        controller._documents = previous


def test_the_welcome_screen_records_no_documents(MWEmptyProject):
    """Recording none while no project is open would tell the next
    launch to open nothing, rather than to open what was there.
    """
    window = MWEmptyProject
    controller = window.windowState
    controller._documents = [0, ["kept"], None]
    was_index = window.stack.currentIndex()
    try:
        window.stack.setCurrentIndex(0)

        assert controller._open_documents() == [0, ["kept"], None]
    finally:
        window.stack.setCurrentIndex(was_index)


# ----------------------------------------- plugin UI is window scope

def test_each_window_owns_its_plugin_user_interface(MWEmptyProject):
    """One per window, which is what it always was -- it owns that
    window's Plugins menu, its panels and its dialogs.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        assert other.pluginUi is not window.pluginUi
        assert other.pluginUi.menu is not window.pluginUi.menu
        assert (
            other.pluginUi.projectPanels
            is not window.pluginUi.projectPanels
        )
    finally:
        other.close()


def test_application_scope_plugin_services_are_shared(MWEmptyProject):
    """State every window reads must be one object. A window with its
    own plugin runtime or option store would enable a plugin nobody
    else could see, or save a routing choice nobody else would read.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        for name in window.pluginUi.SHARED_SERVICES:
            assert getattr(other.pluginUi, name) is getattr(
                window.pluginUi, name
            ), name
    finally:
        other.close()


def test_a_plugin_change_reaches_every_window(MWEmptyProject):
    """Enabling a plugin from one window used to leave the other's
    menus, page types and card styles as they were -- silently, because
    the announcement was made by that window's dialog to itself.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        heard = {"a": 0, "b": 0}
        window.pluginUi.pageTypes.contributionsChanged.connect(
            lambda: heard.__setitem__("a", heard["a"] + 1)
        )
        other.pluginUi.pageTypes.contributionsChanged.connect(
            lambda: heard.__setitem__("b", heard["b"] + 1)
        )

        # What enabling a plugin amounts to, said once.
        window.pluginContributions.announce()

        assert heard == {"a": 1, "b": 1}
    finally:
        other.close()


def test_every_window_shares_one_contribution_service(MWEmptyProject):
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        assert (
            other.pluginContributions is window.pluginContributions
        )
        assert (
            other.pluginUi.contributions
            is window.pluginUi.contributions
        )
    finally:
        other.close()


def test_a_newly_contributed_panel_appears_in_both_windows(
        MWEmptyProject):
    """The declaration was already shared; what was missing was telling
    the other window to look again.
    """
    from PyQt5.QtWidgets import QPlainTextEdit

    from manuskript.plugins.api import (
        ExtensionDescriptor,
        ProjectPanelContribution,
    )

    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    registry = window.pluginRuntime.registry
    try:
        registrar = registry.registrar("vendor.late")
        registrar.register_project_panel(ProjectPanelContribution(
            descriptor=ExtensionDescriptor(
                "vendor.late.panel", "Late panel",
            ),
            widget_factory=lambda context, parent: QPlainTextEdit(
                parent
            ),
            default_file="late/main.txt",
        ))
        registry.install("vendor.late", registrar.contributions)

        window.pluginContributions.announce()

        assert "vendor.late.panel" in window.pluginUi.projectPanels.actions
        assert "vendor.late.panel" in other.pluginUi.projectPanels.actions
    finally:
        registry.remove_plugin("vendor.late")
        window.pluginContributions.announce()
        other.close()


def test_each_window_keeps_its_own_main_tab(MWEmptyProject):
    """Two windows are two places to be working. The project holds one
    answer for which tab was last, so whichever window captured last used
    to win and the other's choice was lost.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        window.tabMain.setCurrentIndex(2)
        other.tabMain.setCurrentIndex(6)

        window.windowState.capture_view_state()
        other.windowState.capture_view_state()

        assert window.windowState._mainTab == 2
        assert other.windowState._mainTab == 6

        # And each is applied to its own window, not to both.
        window.tabMain.setCurrentIndex(0)
        other.tabMain.setCurrentIndex(0)
        window.windowState.restore_view_state(main_tab=6)
        other.windowState.restore_view_state(main_tab=2)

        assert window.tabMain.currentIndex() == 2
        assert other.tabMain.currentIndex() == 6
    finally:
        other.close()


def test_a_window_with_no_recorded_tab_takes_the_projects(
        MWEmptyProject):
    """Which is what a collaborator opening the file for the first time
    gets, and what every window did before views were per window.
    """
    window = MWEmptyProject
    controller = window.windowState
    previous = controller._mainTab
    try:
        controller._mainTab = None
        window.tabMain.setCurrentIndex(0)

        controller.restore_view_state(main_tab=5)

        assert window.tabMain.currentIndex() == 5
    finally:
        controller._mainTab = previous


def test_a_window_that_is_not_the_last_records_its_plugin_docks(
        MWEmptyProject, tmp_path):
    """Closing a window that is not the last never runs the project
    close, so nothing captured its layout. The tool windows went first,
    which takes the plugin docks out of the window, and only then did
    QMainWindow.saveState run -- recording a window those docks had
    already left.

    It has to be a plugin panel: closing tool windows is what removes
    those, so a panel opened straight onto the host would survive and
    show nothing.
    """
    from PyQt5.QtWidgets import QPlainTextEdit

    from manuskript.plugins.api import (
        ExtensionDescriptor,
        ProjectPanelContribution,
    )

    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    store = WorkspaceStateStore(
        QSettings(str(tmp_path / "theirs.ini"), QSettings.IniFormat)
    )
    other.windowState.store = store
    window_id = other.windowId
    registry = window.pluginRuntime.registry
    panel_id = "plugin.vendor.docked.vendor.docked.panel"
    try:
        registrar = registry.registrar("vendor.docked")
        registrar.register_project_panel(ProjectPanelContribution(
            descriptor=ExtensionDescriptor(
                "vendor.docked.panel", "Docked panel",
            ),
            widget_factory=lambda context, parent: QPlainTextEdit(parent),
            default_file="docked/main.txt",
        ))
        registry.install("vendor.docked", registrar.contributions)
        window.pluginContributions.announce()

        assert other.pluginUi.projectPanels.open_panel(
            "vendor.docked.panel"
        ) is not None
        assert panel_id in other.panelHost.instances

        # Not the last window, so this close does not touch the project.
        assert not other.windowRegistry.is_last(other)
        other.close()

        # The dock was still mounted when the arrangement was recorded.
        assert store.load(window_id).panels.get(panel_id) is True
    finally:
        registry.remove_plugin("vendor.docked")
        window.pluginContributions.announce()


def test_a_cancelled_quit_leaves_both_real_windows_open(MWEmptyProject):
    """The case the previous cancel test could not reach.

    That test had the second window refuse to close, so the code never got
    as far as the primary. The real scenario is the other way round: the
    second window closes perfectly well, and then the person cancels the
    save prompt -- which used to leave them with one window gone and the
    application still running.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    manager = window.projectManager
    settled = []
    try:
        manager.session.mark_dirty()
        # Standing in for the person pressing Cancel.
        manager.settleBeforeClosing = lambda: (
            settled.append(True) or False
        )

        assert window.windowRegistry.close_all() is False

        assert settled == [True]
        # Still registered, both of them: the cancelled quit closed
        # nothing. Registry membership rather than isVisible, because the
        # shared test window is never actually shown.
        assert set(window.windowRegistry.workspace_windows) == {
            window, other,
        }
        assert manager.session.is_open
        assert other.projectLifecycleView in (
            window.projectRuntime.views.views
        )
    finally:
        del manager.settleBeforeClosing
        other.close()
