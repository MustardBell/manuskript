from types import SimpleNamespace
from unittest.mock import MagicMock

from manuskript.services.workspace_state import PRIMARY
from manuskript.ui.workspace_windows import (
    ProjectAdoptionViews,
    WorkspaceWindowController,
    WorkspaceWindowViews,
)


def controller_fixture(
        current_id=PRIMARY,
        recorded=(),
        close_result=True,
        saved_state=None,
        intent_for_state=lambda _state: None):
    workspaces = [SimpleNamespace(windowId=current_id)]
    opened = []
    events = []
    store = MagicMock()
    store.open_windows.return_value = tuple(recorded)
    store.load.return_value = saved_state
    controller_holder = {}

    def create(window_id, build_intent=None):
        event = (
            ("create", window_id)
            if build_intent is None
            else ("create", window_id, build_intent)
        )
        events.append(event)
        workspace = SimpleNamespace(windowId=window_id)
        workspaces.append(workspace)
        opened.append(workspace)
        return workspace

    def close_all():
        controller = controller_holder.get("controller")
        if controller is not None and current_id != PRIMARY:
            controller.dispose()
        return close_result

    views = WorkspaceWindowViews(
        current_id=current_id,
        workspaces=lambda: tuple(workspaces),
        identify=lambda workspace: workspace.windowId,
        settle_native_deletions=lambda: events.append(("settle",)),
        create=create,
        close_all=close_all,
        state_store=lambda: store,
        intent_for_state=intent_for_state,
        adoption=ProjectAdoptionViews(
            is_open=lambda: True,
            sync_to_state=lambda value: events.append(("sync", value)),
            connect_project=lambda: events.append(("connect",)),
            apply_loaded_settings=lambda: events.append(("settings",)),
            project_opened=lambda: events.append(("opened",)),
        ),
    )
    controller = WorkspaceWindowController(views)
    controller_holder["controller"] = controller
    return controller, workspaces, opened, store, events


def test_workspace_ids_are_stable_and_action_bool_is_not_an_id():
    controller, workspaces, _opened, _store, _events = (
        controller_fixture()
    )
    workspaces.append(SimpleNamespace(windowId="window-2"))

    opened = controller.open(False)

    assert opened.windowId == "window-3"
    assert controller.open_ids() == [
        PRIMARY,
        "window-2",
        "window-3",
    ]


def test_old_native_windows_are_destroyed_before_a_new_one_is_composed():
    controller, _workspaces, _opened, _store, events = controller_fixture()

    controller.open("window-2")

    assert events == [("settle",), ("create", "window-2")]


def test_declared_membership_is_passed_to_workspace_composition():
    controller, _workspaces, _opened, _store, events = controller_fixture()
    intent = object()

    created = controller.open_with_intent(intent)

    assert created.windowId == "window-2"
    assert events == [
        ("settle",),
        ("create", "window-2", intent),
    ]


def test_new_workspace_adopts_the_running_project_in_order():
    controller, _workspaces, _opened, _store, events = (
        controller_fixture()
    )

    assert controller.adopt_open_project()

    assert events == [
        ("sync", True),
        ("connect",),
        ("settings",),
        ("opened",),
    ]


def test_primary_restores_missing_windows_once():
    controller, _workspaces, opened, _store, _events = (
        controller_fixture(recorded=(PRIMARY, "window-2"))
    )

    first = controller.restore()
    second = controller.restore()

    assert tuple(opened) == first
    assert [workspace.windowId for workspace in first] == ["window-2"]
    assert second == ()


def test_session_restore_composes_each_window_from_saved_membership():
    saved = SimpleNamespace(surfaces=("core.editor",))
    controller, _workspaces, opened, _store, events = controller_fixture(
        recorded=(PRIMARY, "window-2"),
        saved_state=saved,
        intent_for_state=lambda state: ("intent", state.surfaces),
    )

    controller.restore()

    assert [workspace.windowId for workspace in opened] == ["window-2"]
    assert events[-1] == (
        "create", "window-2", ("intent", ("core.editor",)),
    )


def test_secondary_does_not_restore_the_application_session():
    controller, _workspaces, opened, _store, _events = (
        controller_fixture(
            current_id="window-2",
            recorded=(PRIMARY, "window-3"),
        )
    )

    assert controller.restore() == ()
    assert opened == []


def test_quit_records_session_even_when_invoker_is_disposed_by_close():
    controller, workspaces, _opened, store, _events = (
        controller_fixture(current_id="window-2")
    )
    workspaces.insert(0, SimpleNamespace(windowId=PRIMARY))

    assert controller.quit()

    store.set_open_windows.assert_called_once_with(
        [PRIMARY, "window-2"]
    )
    assert controller.views is None


def test_cancelled_quit_does_not_record_a_session():
    controller, _workspaces, _opened, store, _events = (
        controller_fixture(close_result=False)
    )

    assert not controller.quit()

    store.set_open_windows.assert_not_called()
