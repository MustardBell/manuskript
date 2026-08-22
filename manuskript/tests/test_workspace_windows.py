"""Two windows, one project.

This is what the runtime extraction was for. A second window is another
view: it edits the same models, shares the same undo history, and its
closing is not the project's closing. Each window keeps its own
selection, its own open documents and its own panels.
"""

import inspect
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from dataclasses import replace
from weakref import ref

import pytest
from PyQt5.QtCore import QEvent, QPoint, QSettings, Qt
from PyQt5.QtWidgets import QDockWidget, QPlainTextEdit, qApp

from manuskript.panels import (
    PanelContext,
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
)
from manuskript.panels.core import (
    EDITOR,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
)
from manuskript.services.workspace_state import WorkspaceStateStore
from manuskript.services.workspace_window_services import (
    WorkspaceWindowServices,
)


def test_a_window_is_given_services_and_window_scoped_composition_only():
    """A workspace receives shared services and declares its own structure.

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

    assert parameters == [
        "self", "services", "window_id", "build_intent",
    ]


def test_a_second_window_shares_every_application_scope_service(
        MWEmptyProject):
    """Derived from the services themselves, so one added later is covered
    here without anyone remembering to add it.

    The failure this guards is silent: re-listing the services at the
    second construction site and missing one gave that window a fallback
    of its own instead of an error.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
    try:
        assert other.windowId != window.windowId
        assert other.panelRegistry is window.panelRegistry
        assert other.windowRegistry is window.windowRegistry
        assert other.applicationPreferences is window.applicationPreferences
        assert other.mediaTypes is window.mediaTypes
        assert other.pluginContributions is window.pluginContributions
        assert other.testAttribute(Qt.WA_DeleteOnClose)
        assert not window.testAttribute(Qt.WA_DeleteOnClose)
    finally:
        other.close()


def test_workspace_coordination_receives_explicit_ports(MWEmptyProject):
    window = MWEmptyProject
    controller = window.workspaceWindows

    assert controller.views.current_id == window.windowId
    assert controller.views.adoption.is_open()
    assert not hasattr(controller, "window")
    assert not hasattr(controller, "mw")
    assert not hasattr(window, "nextWorkspaceId")
    assert not hasattr(window, "openWorkspaceWindow")
    assert not hasattr(window, "adoptOpenProject")
    assert not hasattr(window, "quitApplication")
    assert not hasattr(window, "openWorkspaceIds")
    assert not hasattr(window, "restoreWorkspaceWindows")
    assert not hasattr(window, "_restoredWorkspaceWindows")


def test_a_second_window_edits_the_same_project(MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        # The project layer is shared, not copied.
        assert other.projectRuntime is window.projectRuntime
        assert other.projectManager is window.projectManager
        assert (
            other.projectRuntime.settingsManager
            is window.projectRuntime.settingsManager
        )
        assert (
            other.projectRuntime.undoStack
            is window.projectRuntime.undoStack
        )
        # And so are the models: editing in one window is editing the
        # project, which is the whole point.
        assert (
            other.projectRuntime.models.outline
            is window.projectRuntime.models.outline
        )
        assert (
            other.projectRuntime.models.characters
            is window.projectRuntime.models.characters
        )
        assert (
            other.projectRuntime.models.plugin_data
            is window.projectRuntime.models.plugin_data
        )
    finally:
        other.close()


def test_each_workspace_owns_only_its_tool_dialogs(MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    first = window.workspaceDialogs.show_targets()
    second = other.workspaceDialogs.show_targets()
    try:
        assert window.workspaceDialogs is not other.workspaceDialogs
        assert not first.isHidden()
        assert not second.isHidden()

        window.closeToolWindows()

        assert first.isHidden()
        assert not second.isHidden()
        assert window.workspaceDialogs.targets_dialog is None
        assert other.workspaceDialogs.targets_dialog is second
    finally:
        other.workspaceDialogs.close_all()
        other.close()


def test_each_workspace_owns_only_its_transfer_dialogs(MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    first = window.workspaceTransfers.show_export()
    second = other.workspaceTransfers.show_export()
    try:
        assert window.workspaceTransfers is not other.workspaceTransfers
        assert first is not second
        assert not first.isHidden()
        assert not second.isHidden()

        window.closeToolWindows()

        assert first.isHidden()
        assert not second.isHidden()
        assert window.workspaceTransfers.export_dialog is None
        assert other.workspaceTransfers.export_dialog is second
    finally:
        other.workspaceTransfers.close_all()
        other.close()


def test_both_windows_are_workspaces_and_neither_is_last(
        MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()

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
    assert not other.projectBinding.bound
    # The first window is alone again, so its close is the project's.
    assert window.windowRegistry.is_last(window)


def test_closing_a_secondary_flushes_and_primary_save_persists_entity_edit(
        MWEmptyProject, tmp_path):
    """A dock-opened entity draft belongs to its window until detach."""
    from manuskript.load_save.project_files import Version1ProjectFiles
    from manuskript.load_save.version_2_codec import Version2ProjectCodec
    from manuskript.services.project_migration import ProjectMigrationService

    window = MWEmptyProject
    manager = window.projectManager
    assert manager.saveDatas()
    source = manager.currentProject
    assert manager.closeProject()
    native_project = tmp_path / "entity-close.msk"
    ProjectMigrationService().upgrade_copy(source, native_project)
    assert manager.loadProject(str(native_project))

    character = manager.createEntity("character", "Pending character")
    other = window.workspaceWindows.open()
    note = "Written in the secondary immediately before it closed."
    try:
        assert other.entityWorkspace.open(character.id)
        dialog = other.entityWorkspace.dialog_for(character.id)
        dialog.bodyEdit.setPlainText(note)
        assert manager.storage.entity_catalog.find(
            character.id
        ).document.text != note

        assert other.close()
        assert manager.storage.entity_catalog.find(
            character.id
        ).document.text == note
        assert manager.saveDatas()

        files = Version1ProjectFiles().read(
            str(native_project), zipped=False
        ).files
        reopened = Version2ProjectCodec().decode(files, zipped=False)
        persisted = next(
            entity for entity in reopened.entities
            if entity.id == character.id
        )
        assert persisted.document.text == note
    finally:
        if other in window.windowRegistry.workspace_windows:
            other.close()
        # The shared fixture must rebuild its original Format 1 manuscript.
        manager.session.mark_dirty()


def test_composed_runtime_reports_status_to_the_active_workspace(
        MWEmptyProject):
    """Exercise the production composition root, not a hand-built registry."""
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        with patch.object(
            window.projectLifecycleView,
            "show_status",
        ) as primary_status, patch.object(
            other.projectLifecycleView,
            "show_status",
        ) as secondary_status:
            window.windowRegistry.activate(other)

            window.projectRuntime.views.show_status("Saved here")

        secondary_status.assert_called_once_with("Saved here", 5000, 1)
        primary_status.assert_not_called()
    finally:
        other.close()


def test_closing_a_secondary_disconnects_application_plugin_updates(
        MWEmptyProject):
    window = MWEmptyProject
    service = window.pluginContributions
    other = window.workspaceWindows.open()
    before = service.receivers(service.changed)

    other.close()

    assert service.receivers(service.changed) == before - 1
    assert other.pluginUi.contributions is None
    assert other.pluginUi.views is None


def test_a_deleted_secondary_window_is_collectable_in_isolation(tmp_path):
    """Exercise native deletion and cyclic collection in another process.

    A stale SIP wrapper terminates Python rather than raising an exception,
    so isolation turns that native failure into an ordinary test result and
    keeps the rest of the suite diagnosable.
    """
    script = """
import gc
import weakref

from PyQt5 import sip
from PyQt5.QtCore import QCoreApplication, QEvent
from PyQt5.QtWidgets import qApp

from manuskript.tests import prepare_test_application

_app, MW = prepare_test_application()

gc.disable()
gc.collect()
window = MW.workspaceWindows.open("collection-probe")
window_ref = weakref.ref(window)
window.close()
qApp.processEvents()
QCoreApplication.sendPostedEvents(window, QEvent.DeferredDelete)
assert sip.isdeleted(window)
del window
gc.collect()
assert window_ref() is None
"""
    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    environment["XDG_DATA_HOME"] = str(tmp_path / "data")
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_each_window_has_its_own_panels(MWEmptyProject):
    """Panels are per window: one window hiding its metadata panel must
    not hide the other's.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        mine = window.panelHost.instance(METADATA)
        theirs = other.panelHost.instance(METADATA)
        assert mine is not theirs
        assert mine.widget is not theirs.widget
        assert mine.action is not theirs.action

        was_visible = not mine.container.isHidden()
        other.panelHost.set_visible(METADATA, True)
        window.panelHost.set_visible(METADATA, False)

        assert not theirs.container.isHidden()
        assert mine.container.isHidden()
    finally:
        # The window is shared with every later test, so its panels are
        # left as they were found.
        window.panelHost.set_visible(METADATA, was_visible)
        other.close()


def test_each_window_has_its_own_tree_and_editor(MWEmptyProject):
    """Its own view of the outline, over the one shared model."""
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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
        self.window.workspaceWindows.reset_restoration(False)
        return self

    def restore(self):
        self.opened = list(self.window.workspaceWindows.restore())
        return self.opened

    def __exit__(self, *_exception):
        for entry in self.opened:
            entry.close()
        self.window.windowState.store = self.previous
        self.window.workspaceWindows.reset_restoration(True)
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
        assert window.workspaceWindows.restore() == ()


def test_a_window_already_open_is_not_opened_twice(
        MWEmptyProject, tmp_path):
    window = MWEmptyProject
    with isolated_session(window, tmp_path, ["main"]) as session:
        assert session.restore() == []
        assert window.workspaceWindows.open_ids().count("main") == 1


def test_only_the_primary_window_restores_a_session(
        MWEmptyProject, tmp_path):
    """Otherwise each reopened window would reopen the session again."""
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
    try:
        with isolated_session(window, tmp_path) as session:
            ids = window.workspaceWindows.open_ids()
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
        self.window.panelRegistry.register(ToolPanelDescriptor(
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
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window) as panel:
            panel.widget.setPlainText("half-written note")
            original = panel.widget

            moved = window.panelPlacement.move_to(
                NOTES, other.panelPlacement,
            )

            assert moved.widget is original
            assert moved.widget.toPlainText() == "half-written note"
            assert moved.host is other.panelHost
            assert other.panelHost.instance(NOTES) is moved
            assert window.panelHost.instance(NOTES) is None
    finally:
        other.close()


def test_a_moved_panel_is_mounted_in_its_new_window(MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window):
            moved = window.panelPlacement.move_to(
                NOTES, other.panelPlacement,
            )

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
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window) as panel:
            old_action = panel.action

            moved = window.panelPlacement.move_to(
                NOTES, other.panelPlacement,
            )

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
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window) as panel:
            # As opened.
            assert panel.action is not None
            panel.action.setChecked(False)
            assert panel.container.isHidden()
            panel.action.setChecked(True)
            assert not panel.container.isHidden()

            # As adopted by another window.
            moved = window.panelPlacement.move_to(
                NOTES, other.panelPlacement,
            )
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
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window):
            assert NOTES in window.toolbar._panelToggles

            window.panelPlacement.move_to(
                NOTES, other.panelPlacement,
            )

            assert NOTES not in window.toolbar._panelToggles
            assert NOTES in other.toolbar._panelToggles
    finally:
        other.close()


def test_a_refused_move_leaves_the_panel_where_it_was(MWEmptyProject):
    """Releasing before the target could refuse would leave the panel
    belonging to nobody -- so the target is asked first.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        instance = window.panelHost.instance(METADATA)

        assert window.panelPlacement.move_to(
            METADATA, other.panelPlacement,
        ) is None

        assert window.panelHost.instance(METADATA) is instance
        assert instance.widget is not None
        assert instance.action is not None
    finally:
        other.close()


def test_a_failed_adoption_rolls_the_living_panel_back(
        MWEmptyProject, monkeypatch):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window) as panel:
            original = panel.widget

            def fail_adoption(_instance):
                raise RuntimeError("destination mount failed")

            monkeypatch.setattr(other.panelHost, "adopt", fail_adoption)
            with pytest.raises(
                RuntimeError,
                match="destination mount failed",
            ):
                window.panelPlacement.move_to(
                    NOTES,
                    other.panelPlacement,
                )

            restored = window.panelHost.instance(NOTES)
            assert restored.widget is original
            assert restored.host is window.panelHost
            assert other.panelHost.instance(NOTES) is None
            assert NOTES in window.toolbar._panelToggles
            assert NOTES not in other.toolbar._panelToggles
    finally:
        other.close()


def test_moving_a_panel_to_its_own_window_changes_nothing(
        MWEmptyProject):
    window = MWEmptyProject
    instance = window.panelHost.instance(METADATA)

    assert window.panelPlacement.move_to(
        METADATA, window.panelPlacement,
    ) is instance
    assert window.panelHost.instance(METADATA) is instance


def test_panel_placement_receives_explicit_workspace_ports(
        MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        controller = window.panelPlacement

        assert controller.target.host is window.panelHost
        assert controller.views.targets() == (
            other.panelPlacement.target,
        )
        assert not hasattr(controller, "window")
        assert not hasattr(controller, "mw")
        assert not hasattr(window, "movePanelTo")
        assert not hasattr(window, "togglePanelFloating")
        assert not hasattr(window, "buildPanelMoveMenu")
        assert not hasattr(window, "buildPanelFloatMenu")
        assert not hasattr(window, "menuMovePanel")
        assert not hasattr(window, "menuFloatPanel")
    finally:
        other.close()


def test_the_menu_offers_the_same_thing_however_many_windows_are_open(
        MWEmptyProject):
    """A menu that changes shape with the window count teaches nobody.

    Whether a fresh workspace could take a given panel is not knowable from
    the descriptor, and guessing it from the peers that happen to be open
    made the offer appear and disappear for reasons a reader cannot see.
    So it is offered uniformly, and the window is undone when there turns
    out to be nothing to hand over.
    """

    window = MWEmptyProject

    def first_entries():
        window.panelPlacement.build_move_menu()
        return {
            action.menu().menuAction().data(): [
                entry.text() for entry in action.menu().actions()
                if not entry.isSeparator()
            ][0]
            for action in window.panelPlacement.move_menu.actions()
            if action.menu() is not None
        }

    alone = first_entries()
    other = window.workspaceWindows.open()
    try:
        with_peer = first_entries()
    finally:
        other.close()

    assert alone, "every owned panel is offered somewhere to go"
    assert set(alone) == set(with_peer)
    assert set(alone.values()) == {"New window"}
    assert set(with_peer.values()) == {"New window"}


def test_a_peer_that_can_take_a_panel_is_offered_beside_a_new_window(
        MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        with movable_panel(window):
            window.panelPlacement.build_move_menu()

            submenu = next(
                action.menu()
                for action in window.panelPlacement.move_menu.actions()
                if action.menu() is not None
                and action.menu().title() == "Movable notes"
            )

            offered = [
                action.text() for action in submenu.actions()
                if not action.isSeparator()
            ]
            assert offered[0] == "New window"
            assert len(offered) == 2
    finally:
        other.close()


def test_a_panel_can_leave_even_when_no_other_window_is_open(MWEmptyProject):
    """There is always somewhere to go, because one can be made."""

    window = MWEmptyProject

    window.panelPlacement.build_move_menu()

    submenus = [
        action.menu()
        for action in window.panelPlacement.move_menu.actions()
        if action.menu() is not None
    ]
    assert submenus
    for submenu in submenus:
        assert [action.text() for action in submenu.actions()] == [
            "New window"
        ]


def test_a_move_menu_does_not_retain_a_closed_target(MWEmptyProject):
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    with movable_panel(window):
        window.panelPlacement.build_move_menu()
        destination = ref(other.panelPlacement.target)

        other.close()

        assert destination() is None


# ---------------------------------------- arranging docks in one window

def test_every_existing_dock_gets_precise_context_commands(MWEmptyProject):
    window = MWEmptyProject

    assert window.dckSearch.contextMenuPolicy() == Qt.CustomContextMenu
    assert (
        window.panelHost.instance(PROJECT_TREE).container.contextMenuPolicy()
        == Qt.CustomContextMenu
    )


def test_a_late_plugin_dock_gets_the_same_context_commands(MWEmptyProject):
    window = MWEmptyProject

    with movable_panel(window) as panel:
        assert panel.container.contextMenuPolicy() == Qt.CustomContextMenu
        assert panel.container in window.panelPlacement._dock_context_slots


def test_arrange_menu_discovers_late_panels_without_a_hardcoded_list(
        MWEmptyProject):
    window = MWEmptyProject

    with movable_panel(window) as panel:
        window.dckSearch.show()
        window.panelPlacement.build_arrange_menu()
        offered = {
            action.data()
            for action in window.panelPlacement.arrange_menu.actions()
            if action.menu() is not None
        }

        assert panel.container.objectName() in offered
        assert window.dckSearch.objectName() in offered


def test_edge_command_moves_a_panel_and_saved_state_remembers_it(
        MWEmptyProject):
    window = MWEmptyProject
    dock = window.panelHost.instance(METADATA).container
    before = window.saveState()
    try:
        assert window.panelPlacement.move_to_edge(
            dock, Qt.LeftDockWidgetArea,
        )
        assert window.dockWidgetArea(dock) == Qt.LeftDockWidgetArea
        assert window.panelHost.instance(METADATA).action.isChecked()

        arranged = window.saveState()
        window.panelPlacement.move_to_edge(dock, Qt.RightDockWidgetArea)
        assert window.restoreState(arranged)
        assert window.dockWidgetArea(dock) == Qt.LeftDockWidgetArea
    finally:
        window.restoreState(before)


def test_tab_command_uses_qt_layout_and_survives_state_restore(
        MWEmptyProject):
    window = MWEmptyProject
    tree = window.panelHost.instance(PROJECT_TREE).container
    metadata = window.panelHost.instance(METADATA).container
    before = window.saveState()
    try:
        window.panelHost.reveal(PROJECT_TREE)
        window.panelHost.reveal(METADATA)
        assert window.panelPlacement.tab_with(metadata, tree)
        assert metadata in window.tabifiedDockWidgets(tree)

        arranged = window.saveState()
        window.panelPlacement.move_to_edge(
            metadata, Qt.LeftDockWidgetArea,
        )
        assert window.restoreState(arranged)
        assert metadata in window.tabifiedDockWidgets(tree)
    finally:
        window.restoreState(before)


# ------------------------------------------------- tearing a panel off

def test_a_torn_off_panel_floats_free_of_the_layout(MWEmptyProject):
    """A floating dock, keeping the same widget: the panel leaves the
    splitter without being rebuilt.
    """
    window = MWEmptyProject
    original = window.panelHost.instance(METADATA).widget
    try:
        floated = window.panelPlacement.toggle_floating(METADATA)

        assert floated.widget is original
        assert floated.container is not None
        assert floated.container.isFloating()
        assert METADATA in window.panelHost.floating()
        assert not window.corePanels.editor.isAncestorOf(original)
    finally:
        window.panelPlacement.toggle_floating(METADATA)


def test_a_floating_panel_is_not_a_workspace_window(MWEmptyProject):
    """So it can neither keep a project open nor answer for the last
    close -- which a real second window would.
    """
    window = MWEmptyProject
    try:
        floated = window.panelPlacement.toggle_floating(METADATA)

        assert floated.container not in (
            window.windowRegistry.workspace_windows
        )
        assert window.windowRegistry.is_last(window)
        assert len(window.windowRegistry.workspace_windows) == 1
    finally:
        window.panelPlacement.toggle_floating(METADATA)


def test_redocking_returns_the_panel_to_a_dock_area(MWEmptyProject):
    """Core panels return as native docks, not fixed splitter children."""
    window = MWEmptyProject
    original = window.panelHost.instance(METADATA).widget
    window.panelPlacement.toggle_floating(METADATA)

    redocked = window.panelPlacement.toggle_floating(METADATA)

    assert redocked.widget is original
    assert window.panelHost.floating() == ()
    assert redocked.container is not None
    assert not redocked.container.isFloating()
    assert window.dockWidgetArea(redocked.container) != Qt.NoDockWidgetArea


def test_a_torn_off_panel_keeps_its_model_bindings(MWEmptyProject):
    """The binding is to the project's models, which belong to the
    runtime -- so floating the panel cannot break it.
    """
    window = MWEmptyProject
    panel = window.panelHost.instance(METADATA).widget
    before = panel.properties.txtTitle._model
    assert before is window.projectRuntime.models.outline
    try:
        window.panelPlacement.toggle_floating(METADATA)

        assert panel.properties.txtTitle._model is before
        assert (
            panel.properties.txtGoal._model
            is window.projectRuntime.models.outline
        )
    finally:
        window.panelPlacement.toggle_floating(METADATA)


def test_a_torn_off_panel_is_still_toggled_from_the_toolbar(
        MWEmptyProject):
    window = MWEmptyProject
    try:
        floated = window.panelPlacement.toggle_floating(METADATA)

        assert METADATA in window.toolbar._panelToggles
        floated.action.setChecked(False)
        assert floated.container.isHidden()
        floated.action.setChecked(True)
        assert not floated.container.isHidden()
    finally:
        window.panelPlacement.toggle_floating(METADATA)


def test_the_float_menu_marks_what_is_already_floating(MWEmptyProject):
    window = MWEmptyProject
    try:
        window.panelPlacement.toggle_floating(METADATA)

        window.panelPlacement.build_float_menu()

        # By panel id, not by the text on the entry: the interface is
        # translated, and this test should not depend on the locale.
        checked = {
            action.data(): action.isChecked()
            for action in window.panelPlacement.floating_menu.actions()
        }
        assert checked[METADATA] is True
        assert checked[STORYLINE] is False
    finally:
        window.panelPlacement.toggle_floating(METADATA)


def test_tearing_off_twice_is_not_two_floats(MWEmptyProject):
    window = MWEmptyProject
    try:
        first = window.panelHost.tear_off(METADATA)
        again = window.panelHost.tear_off(METADATA)

        assert again is first
        assert window.panelHost.floating() == (METADATA,)
    finally:
        window.panelHost.redock(METADATA)


def test_redocking_keeps_core_panels_out_of_editor_splitters(MWEmptyProject):
    """Native docks must not return as fixed children of editor splitters."""
    window = MWEmptyProject
    original = window.panelHost.instance(METADATA).widget

    window.panelPlacement.toggle_floating(METADATA)
    redocked = window.panelPlacement.toggle_floating(METADATA)

    assert redocked.widget is original
    assert not window.corePanels.editor.isAncestorOf(original)
    assert window.dockWidgetArea(redocked.container) != Qt.NoDockWidgetArea


# ------------------------------------------- documents are per window

def test_each_window_records_its_own_open_documents(
        MWEmptyProject, tmp_path):
    """Two windows on one project are two places to be reading, so the
    project's single list of open documents is not enough to describe
    them.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    was_active = window._projectSurfaceActive
    try:
        window._projectSurfaceActive = False

        assert controller._open_documents() == [0, ["kept"], None]
    finally:
        window._projectSurfaceActive = was_active


# ----------------------------------------- plugin UI is window scope

def test_each_window_owns_its_plugin_user_interface(MWEmptyProject):
    """One per window, which is what it always was -- it owns that
    window's Plugins menu, its panels and its dialogs.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        assert other.pluginUi is not window.pluginUi
        assert other.pluginUi.menu is not window.pluginUi.menu
        assert (
            other.pluginUi.projectPanels
            is not window.pluginUi.projectPanels
        )
    finally:
        other.close()


def test_plugin_ui_has_no_main_window_service_locator(MWEmptyProject):
    controller = MWEmptyProject.pluginUi

    assert not hasattr(controller, "window")
    assert not hasattr(controller.views, "window")


def test_application_scope_plugin_services_are_shared(MWEmptyProject):
    """State every window reads must be one object. A window with its
    own plugin runtime or option store would enable a plugin nobody
    else could see, or save a routing choice nobody else would read.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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


def test_each_window_keeps_its_own_active_surface(MWEmptyProject):
    """Two windows keep independent semantic locations."""
    from manuskript.panels.core import EDITOR, GENERAL, OUTLINE

    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        window.activatePanel(GENERAL)
        other.activatePanel(EDITOR)

        window.windowState.capture_view_state()
        other.windowState.capture_view_state()

        assert window.windowState._activeSurface == GENERAL
        assert other.windowState._activeSurface == EDITOR

        # And each is applied to its own window, not to both.
        window.activatePanel(OUTLINE)
        other.activatePanel(OUTLINE)
        window.windowState.restore_view_state()
        other.windowState.restore_view_state()

        assert window.surfaceHost.current() == GENERAL
        assert other.surfaceHost.current() == EDITOR
    finally:
        other.close()


def test_focusing_a_tool_panel_is_not_where_this_window_was(MWEmptyProject):
    """The two facts the old single field ran together.

    Semantic focus may land in the project tree, which is a tool panel.
    Filing that as the window's surface meant the next launch tried to go
    somewhere the navigator does not list -- and it was written into
    version 4 as though it were an answer.
    """
    from manuskript.panels.core import OUTLINE, PROJECT_TREE

    window = MWEmptyProject
    window.activatePanel(OUTLINE)

    window.notePanelFocus(PROJECT_TREE)
    window.windowState.capture_view_state()

    assert window._activePanelId == PROJECT_TREE
    assert window.windowState._activeSurface == OUTLINE


def test_a_window_with_no_recorded_panel_migrates_the_projects_tab(
        MWEmptyProject):
    from manuskript.panels.core import OUTLINE

    window = MWEmptyProject
    controller = window.windowState
    previous_surface = controller._activeSurface
    previous_tab = controller._legacyMainTab
    try:
        controller._activeSurface = None
        controller._legacyMainTab = None

        controller.restore_view_state(main_tab=5)

        assert window.surfaceHost.current() == OUTLINE
    finally:
        controller._activeSurface = previous_surface
        controller._legacyMainTab = previous_tab


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
    other = window.workspaceWindows.open()
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
    other = window.workspaceWindows.open()
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


def test_moving_a_panel_to_a_new_window_gives_it_a_workspace(MWEmptyProject):
    """The whole point of the entry, and the answer to a window report.

    Floating a panel makes a QDockWidget owned by this window: no taskbar
    entry of its own, no minimize or maximize, raising with its owner, and
    unable to hold a second panel. A reader who tore an editor out and then
    wanted the project tree beside it was asking for a workspace. This makes
    one and hands the panel to it.
    """

    window = MWEmptyProject
    before = set(window.windowRegistry.workspace_windows)

    with movable_panel(window) as panel:
        panel_id = panel.descriptor.id

        moved = window.panelPlacement.move_to_new_window(panel_id)

        try:
            created = [
                candidate
                for candidate in window.windowRegistry.workspace_windows
                if candidate not in before
            ]
            assert len(created) == 1
            fresh = created[0]
            # A workspace, not a dock: registered, unparented, and able to
            # hold panels of its own.
            assert fresh.parent() is None
            assert moved is not None
            assert fresh.panelHost.instance(panel_id) is not None
            assert window.panelHost.instance(panel_id) is None
        finally:
            for candidate in window.windowRegistry.workspace_windows:
                if candidate not in before:
                    candidate.close()


def test_a_workspace_that_cannot_be_made_leaves_the_panel_where_it_was(
        MWEmptyProject):
    """Made first, handed over second, so a failure loses nothing."""

    window = MWEmptyProject

    with movable_panel(window) as panel:
        panel_id = panel.descriptor.id
        window.panelPlacement.views = replace(
            window.panelPlacement.views, open_workspace=lambda: None
        )

        assert window.panelPlacement.move_to_new_window(panel_id) is None
        assert window.panelHost.instance(panel_id) is not None


def test_a_surface_the_navigator_offers_is_a_window_not_a_dock(
        MWEmptyProject):
    """The user's rule: anything navigation has is not a dock.

    It may be docked, and docked it may fill most of the frame, but that is
    a placement rather than what it is. Floating one does not give it a
    window of its own -- it gives it a utility window owned by this one,
    with no taskbar entry, no minimize or maximize, raising with its owner
    and unable to hold anything else. That is what a reader got when they
    dragged an editor out, so Qt is not offered the chance.
    """

    window = MWEmptyProject

    editor = window.surfaceHost.instance(EDITOR)
    tree = window.panelHost.instance(PROJECT_TREE)

    # Asked of the type, not of a field. Reading .navigator to find out
    # which kind something is was the habit the split ended -- and a tool
    # panel has no such field to read any more.
    assert isinstance(editor.descriptor, WorkspaceSurfaceDescriptor)
    assert isinstance(tree.descriptor, ToolPanelDescriptor)
    # The rule is structural now rather than argued. There is no dock to
    # take Qt's floatable feature away from: the editor is a page of the
    # window, and the panel host it used to be docked in has never heard
    # of it. A tool panel still floats, which is what a dock is for.
    assert editor.container is None
    assert window.panelHost.instance(EDITOR) is None
    assert window.tabMain.indexOf(editor.widget) != -1
    assert tree.container.features() & QDockWidget.DockWidgetFloatable


def test_the_float_menu_leaves_out_the_surfaces_that_are_windows(
        MWEmptyProject):
    window = MWEmptyProject

    window.panelPlacement.build_float_menu()

    offered = {
        action.data()
        for action in window.panelPlacement.floating_menu.actions()
        if action.data()
    }
    assert EDITOR not in offered
    assert PROJECT_TREE in offered


def test_the_view_menu_offers_each_owned_surface_to_a_new_window(
        MWEmptyProject):
    window = MWEmptyProject

    window.surfaceTransfer.build_menu()

    actions = {
        action.data(): action
        for action in window.surfaceTransfer.views.menu.actions()
    }
    assert set(actions) == set(window.surfaceHost.instances)
    assert actions[EDITOR].isEnabled()
    assert "new workspace window" in actions[EDITOR].statusTip()


def test_dragging_a_surface_row_starts_the_same_transfer_gesture(
        MWEmptyProject):
    window = MWEmptyProject
    controller = window.surfaceTransfer
    row = window.navigator.row_for_panel(EDITOR)
    item = window.lstTabs.item(row)
    start = window.lstTabs.visualItemRect(item).center()
    assert item.text() in item.toolTip()
    assert item.toolTip() != item.text()

    class Mouse:
        def __init__(self, kind, position, button, buttons):
            self._kind = kind
            self._position = position
            self._button = button
            self._buttons = buttons

        def type(self):
            return self._kind

        def pos(self):
            return self._position

        def button(self):
            return self._button

        def buttons(self):
            return self._buttons

    press = Mouse(
        QEvent.MouseButtonPress,
        start,
        Qt.LeftButton,
        Qt.LeftButton,
    )
    move = Mouse(
        QEvent.MouseMove,
        start + QPoint(qApp.startDragDistance() + 1, 0),
        Qt.NoButton,
        Qt.LeftButton,
    )

    with patch.object(controller, "_drag_to_new_workspace") as drag:
        assert not controller.eventFilter(window.lstTabs, press)
        assert controller.eventFilter(window.lstTabs, move)

    drag.assert_called_once_with(EDITOR)


def test_only_the_explicit_drop_target_completes_a_surface_drag(
        MWEmptyProject):
    controller = MWEmptyProject.surfaceTransfer

    with patch.object(
        controller,
        "move_to_new_window",
        return_value="moved",
    ) as move:
        assert controller.complete_drag(
            EDITOR, Qt.IgnoreAction, None,
        ) is None
        assert controller.complete_drag(
            EDITOR, Qt.MoveAction, "core.outline",
        ) is None
        assert controller.complete_drag(
            EDITOR, Qt.MoveAction, EDITOR,
        ) == "moved"

    move.assert_called_once_with(EDITOR)


def test_surface_drop_target_is_named_and_has_wcag_text_contrast(
        MWEmptyProject):
    from manuskript.ui.tooltip_style import contrast_ratio

    target = MWEmptyProject.surfaceTransfer._drop_target

    assert target.accessibleName()
    assert target.accessibleDescription()
    assert contrast_ratio(
        target._foreground_color,
        target._background_color,
    ) >= 4.5


def test_move_surface_composes_a_new_window_for_the_living_editor(
        MWEmptyProject, tmp_path):
    """The command transfers the Editor instead of making a second one."""

    window = MWEmptyProject
    before = set(window.windowRegistry.workspace_windows)
    original_editor = window.mainEditor
    controller = window.surfaceTransfer
    previous_views = controller.views
    previous_store = window.windowState.store
    state_store = WorkspaceStateStore(QSettings(
        str(tmp_path / "surface-membership.ini"),
        QSettings.IniFormat,
    ))
    events = []

    def flush():
        events.append(("flush", window.surfaceHost.contains(EDITOR)))
        previous_views.flush_pending_edits()

    def create(intent):
        events.append(("create", window.surfaceHost.contains(EDITOR)))
        return previous_views.create_workspace(intent)

    controller.views = replace(
        previous_views,
        flush_pending_edits=flush,
        create_workspace=create,
    )

    try:
        moved = controller.move_to_new_window(EDITOR)
    finally:
        controller.views = previous_views
    created = [
        candidate
        for candidate in window.windowRegistry.workspace_windows
        if candidate not in before
    ]
    try:
        assert moved is not None
        assert len(created) == 1
        fresh = created[0]
        assert set(fresh.surfaceHost.instances) == {EDITOR}
        assert fresh.mainEditor is original_editor
        assert moved.host is fresh.surfaceHost
        assert events == [("flush", True), ("create", False)]
        assert not window.surfaceHost.contains(EDITOR)
        assert fresh.isVisible()
        window.windowState.store = state_store
        fresh.windowState.store = state_store
        window.windowState.save()
        fresh.windowState.save()
        assert EDITOR not in state_store.load(window.windowId).surfaces
        assert state_store.load(fresh.windowId).surfaces == (EDITOR,)
        fresh.surfaceTransfer.build_menu()
        editor_action = next(
            action
            for action in fresh.surfaceTransfer.views.menu.actions()
            if action.data() == EDITOR
        )
        assert not editor_action.isEnabled()
        assert "must keep at least one surface" in editor_action.statusTip()
    finally:
        for candidate in created:
            if candidate.surfaceHost.contains(EDITOR):
                window.surfaceHost.attach(
                    candidate.surfaceHost.detach(EDITOR)
                )
            candidate.close()
        window.windowState.store = previous_store

    assert window.mainEditor is original_editor


def test_a_failed_surface_move_restores_ownership_and_active_view(
        MWEmptyProject):
    window = MWEmptyProject
    controller = window.surfaceTransfer
    original = window.surfaceHost.instance(EDITOR)
    window.surfaceHost.activate(EDITOR)
    previous_views = controller.views
    before = set(window.windowRegistry.workspace_windows)

    controller.views = replace(
        previous_views,
        show_status=lambda *_args: None,
    )
    try:
        with patch.object(
            type(window.workspaceWindows),
            "adopt_open_project",
            side_effect=RuntimeError("destination failed"),
        ), patch("manuskript.ui.surface_transfer.LOGGER.exception"):
            assert controller.move_to_new_window(EDITOR) is None
    finally:
        controller.views = previous_views

    assert set(window.windowRegistry.workspace_windows) == before
    assert window.surfaceHost.instance(EDITOR) is original
    assert original.host is window.surfaceHost
    assert window.surfaceHost.current() == EDITOR


def test_a_workspace_can_be_composed_for_one_living_surface(
        MWEmptyProject):
    """Sparse membership is an input, not widgets removed after wiring."""
    from manuskript.services.workspace_state import WorkspaceStateStore
    from manuskript.panels.core import OUTLINE
    from manuskript.ui.workspace_surfaces import WorkspaceBuildIntent

    window = MWEmptyProject
    fresh_id = "window-sparse-editor"
    WorkspaceStateStore().forget(fresh_id)
    other = type(window)(
        window.services,
        window_id=fresh_id,
        build_intent=WorkspaceBuildIntent(
            surface_ids=(EDITOR,),
            active_surface=EDITOR,
        ),
    )
    try:
        other.workspaceWindows.adopt_open_project()

        assert set(other.surfaceHost.instances) == {EDITOR}
        assert other.surfaceHost.current() == EDITOR
        assert other.mainEditor.editor_context is not None
        assert other.navigator.row_for_panel(EDITOR) is not None
        assert other.navigator.row_for_panel(OUTLINE) is None
        with pytest.raises(LookupError):
            _ = other.corePanels.outline
    finally:
        other.close()
        WorkspaceStateStore().forget(fresh_id)


def test_a_living_editor_takes_its_project_bindings_to_a_sparse_window(
        MWEmptyProject):
    from manuskript.models.outlineItem import outlineItem
    from manuskript.services.workspace_state import WorkspaceStateStore
    from manuskript.ui.workspace_surfaces import WorkspaceBuildIntent

    window = MWEmptyProject
    original = window.mainEditor
    item = outlineItem(title="Travelling scene", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    original.setCurrentModelIndex(index, newTab=True)
    open_editor = original.currentEditor()
    moved = window.surfaceHost.detach(EDITOR)
    fresh_id = "window-transferred-editor"
    WorkspaceStateStore().forget(fresh_id)
    other = None
    try:
        other = type(window)(
            window.services,
            window_id=fresh_id,
            build_intent=WorkspaceBuildIntent.for_transfer(moved),
        )
        other.workspaceWindows.adopt_open_project()

        assert other.mainEditor is original
        assert other.mainEditor.currentEditor() is open_editor
        assert (
            open_editor.editor_context.text_editor
            is other.projectBinding.text_editor_context
        )
        assert other.mainEditor.editor_context is not None
        assert EDITOR not in window.projectBinding._surfaces
        assert other.projectBinding._surfaces[EDITOR] is moved
        with pytest.raises(AttributeError):
            _ = window.mainEditor
        with pytest.raises(LookupError):
            _ = window.corePanels.editor
    finally:
        if other is not None and other.surfaceHost.contains(EDITOR):
            window.surfaceHost.attach(other.surfaceHost.detach(EDITOR))
        if other is not None:
            other.close()
        WorkspaceStateStore().forget(fresh_id)

    assert window.mainEditor is original
    assert window.mainEditor.editor_context is not None


def test_a_legacy_floating_editor_becomes_the_same_living_peer_workspace(
        MWEmptyProject, tmp_path):
    """The dock-era float is migration input, not a view to reconstruct."""

    from manuskript.ui.legacy_layouts import LegacySurfaceLayout

    window = MWEmptyProject
    original_editor = window.mainEditor
    controller = window.workspaceWindows
    previous_views = controller.views
    previous_store = window.windowState.store
    shared_store = WorkspaceStateStore(QSettings(
        str(tmp_path / "legacy-floating-surface.ini"),
        QSettings.IniFormat,
    ))
    window.windowState.store = shared_store
    controller.reset_restoration(False)
    layout = LegacySurfaceLayout(
        surface_id=EDITOR,
        floating=True,
        geometry=(120, 90, 640, 480),
    )
    migration = previous_views.legacy_migration

    def save_in_shared_store(workspace):
        workspace.windowState.store = shared_store
        workspace.windowState.save()

    controller.views = replace(
        previous_views,
        legacy_migration=replace(
            migration,
            floating_surfaces=lambda: (layout,),
            save_workspace=save_in_shared_store,
        ),
    )
    created = []
    try:
        created = list(controller.restore())

        assert len(created) == 1
        peer = created[0]
        assert set(peer.surfaceHost.instances) == {EDITOR}
        assert peer.mainEditor is original_editor
        assert not window.surfaceHost.contains(EDITOR)
        peer_geometry = peer.geometry()
        available = qApp.desktop().availableGeometry(peer)
        assert peer_geometry.x() == max(
            available.left(),
            min(120, available.right() - peer_geometry.width() + 1),
        )
        assert peer_geometry.y() == max(
            available.top(),
            min(90, available.bottom() - peer_geometry.height() + 1),
        )
        # A full workspace has more chrome than its historical dock shell.
        # Preserve the requested size unless the usable window's own minimum
        # is larger; never force it into a clipped 640-pixel frame.
        assert peer_geometry.width() >= 640
        assert peer_geometry.height() >= 480
        assert EDITOR not in shared_store.load(window.windowId).surfaces
        assert shared_store.load(peer.windowId).surfaces == (EDITOR,)
        assert shared_store.open_windows() == (
            window.windowId,
            peer.windowId,
        )
    finally:
        for peer in created:
            if peer.surfaceHost.contains(EDITOR):
                window.surfaceHost.attach(peer.surfaceHost.detach(EDITOR))
            peer.close()
        controller.views = previous_views
        controller.reset_restoration(True)
        window.windowState.store = previous_store

    assert window.mainEditor is original_editor
