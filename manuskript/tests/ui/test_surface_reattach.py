"""A detached surface can return and retire its temporary workspace."""

from dataclasses import replace

from PyQt5.QtWidgets import qApp

from manuskript.panels.core import EDITOR


def settle():
    for _turn in range(5):
        qApp.processEvents()


def detach_editor(source):
    source.activatePanel(EDITOR)
    original = source.surfaceHost.instance(EDITOR)
    workspace = source.surfaceTransfer.move_to_new_workspace(EDITOR)
    assert workspace is not None
    assert set(workspace.surfaceHost.instances) == {EDITOR}
    assert workspace.surfaceHost.instance(EDITOR) is original
    return original, workspace


def return_editor_if_needed(source, workspace):
    if (
        workspace is not None
        and workspace.surfaceHost.contains(EDITOR)
        and not source.surfaceHost.contains(EDITOR)
    ):
        returned = workspace.surfaceHost.detach(EDITOR)
        source.surfaceHost.attach(returned)
        source.activatePanel(EDITOR)
    if workspace is not None and workspace in (
        source.windowRegistry.workspace_windows
    ):
        workspace.close()
        settle()


def test_reattach_preserves_identity_and_closes_the_empty_wrapper(
        MWEmptyProject):
    source = MWEmptyProject
    original, wrapper = detach_editor(source)
    widget = original.widget

    try:
        moved = wrapper.surfaceTransfer.move_to_workspace(
            EDITOR, source,
        )
        settle()

        assert moved is original
        assert moved.widget is widget
        assert moved.host is source.surfaceHost
        assert source.surfaceHost.instance(EDITOR) is original
        assert original.container.parentWidget() is source
        assert wrapper not in source.windowRegistry.workspace_windows
    finally:
        return_editor_if_needed(source, wrapper)


def test_a_sparse_wrapper_offers_existing_workspaces_but_not_another_new_one(
        MWEmptyProject):
    source = MWEmptyProject
    _original, wrapper = detach_editor(source)
    try:
        wrapper.surfaceTransfer.build_menu()
        editor_menu = next(
            action.menu()
            for action in wrapper.surfaceTransfer.views.menu.actions()
            if action.data() == EDITOR
        )
        actions = editor_menu.actions()
        new_window = actions[0]
        destinations = [
            action for action in actions[1:]
            if not action.isSeparator()
        ]

        assert not new_window.isEnabled()
        assert len(destinations) == 1
        assert destinations[0].isEnabled()
        assert destinations[0].data() == (EDITOR, source.windowId)
    finally:
        return_editor_if_needed(source, wrapper)


def test_failed_destination_activation_rolls_the_living_surface_back(
        MWEmptyProject):
    source = MWEmptyProject
    original, wrapper = detach_editor(source)
    controller = wrapper.surfaceTransfer
    previous_views = controller.views
    controller.views = replace(
        previous_views,
        activate_workspace_surface=lambda _workspace, _surface_id: False,
    )
    try:
        assert controller.move_to_workspace(EDITOR, source) is None

        assert wrapper.surfaceHost.instance(EDITOR) is original
        assert original.host is wrapper.surfaceHost
        assert not source.surfaceHost.contains(EDITOR)
        assert wrapper in source.windowRegistry.workspace_windows
    finally:
        controller.views = previous_views
        return_editor_if_needed(source, wrapper)


def test_a_primary_workspace_cannot_move_away_its_last_surface(
        MWEmptyProject):
    source = MWEmptyProject
    original, wrapper = detach_editor(source)
    controller = wrapper.surfaceTransfer
    previous_views = controller.views
    controller.views = replace(previous_views, close_when_empty=False)
    try:
        assert controller.move_to_workspace(EDITOR, source) is None

        assert wrapper.surfaceHost.instance(EDITOR) is original
        assert not source.surfaceHost.contains(EDITOR)
        assert wrapper in source.windowRegistry.workspace_windows
    finally:
        controller.views = previous_views
        return_editor_if_needed(source, wrapper)
