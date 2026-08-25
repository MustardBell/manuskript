"""A detached surface can return and retire its temporary workspace."""

from dataclasses import replace

import pytest

from PyQt5.QtWidgets import QDockWidget, qApp

from manuskript.panels.core import (
    CORE_SURFACE_IDS,
    EDITOR,
    METADATA,
    PROJECT_TREE,
    STORYLINE,
)


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


def test_a_transfer_wrapper_shows_the_surface_without_workspace_passengers(
        MWEmptyProject):
    source = MWEmptyProject
    _original, wrapper = detach_editor(source)
    try:
        settle()

        assert wrapper.dckNavigation.isHidden()
        editor_dock = wrapper.surfaceHost.instance(EDITOR).container
        assert not editor_dock.isHidden()
        assert not editor_dock.features() & QDockWidget.DockWidgetClosable
        assert wrapper.panelHost.instance(PROJECT_TREE) is None
        assert wrapper.panelHost.instance(METADATA) is None
        assert wrapper.panelHost.instance(STORYLINE) is None
        assert (
            wrapper.outlineSelection.selectionModel().model()
            is wrapper.projectRuntime.models.outline
        )
    finally:
        return_editor_if_needed(source, wrapper)


@pytest.mark.parametrize(
    "surface_id",
    tuple(item for item in CORE_SURFACE_IDS if item != EDITOR),
)
def test_a_non_editor_transfer_constructs_no_core_tool_panels(
        MWEmptyProject, surface_id):
    source = MWEmptyProject
    source.activatePanel(surface_id)
    original = source.surfaceHost.instance(surface_id)
    wrapper = source.surfaceTransfer.move_to_new_workspace(surface_id)
    assert wrapper is not None
    try:
        settle()

        assert tuple(wrapper.panelHost.instances) == ()
        assert set(wrapper.surfaceHost.instances) == {surface_id}
        assert wrapper.surfaceHost.instance(surface_id) is original
    finally:
        if wrapper.surfaceHost.contains(surface_id):
            wrapper.surfaceTransfer.move_to_workspace(surface_id, source)
        settle()


def test_closing_a_transfer_wrapper_returns_its_unique_editor(
        MWEmptyProject):
    from manuskript.models.outlineItem import outlineItem

    source = MWEmptyProject
    original, wrapper = detach_editor(source)
    widget = original.widget
    item = outlineItem(title="Returned scene", _type="md")
    source.projectRuntime.models.outline.appendItem(item)
    index = source.projectRuntime.models.outline.indexFromItem(item)

    assert wrapper.close()
    settle()

    assert wrapper not in source.windowRegistry.workspace_windows
    assert source.surfaceHost.instance(EDITOR) is original
    assert original.widget is widget
    assert original.container.parentWidget() is source

    tree = source.corePanels.project_tree.tree
    tree.setCurrentIndex(index)
    settle()

    assert source.activatePanel(EDITOR)
    assert source.mainEditor.currentEditor().currentIndex == index


def test_a_wrapper_refuses_to_close_if_its_editor_cannot_be_preserved(
        MWEmptyProject, monkeypatch):
    source = MWEmptyProject
    original, wrapper = detach_editor(source)
    attach = source.surfaceHost.attach

    def reject(_instance):
        raise RuntimeError("destination rejected surface")

    monkeypatch.setattr(source.surfaceHost, "attach", reject)
    try:
        assert not wrapper.close()
        settle()

        assert wrapper in source.windowRegistry.workspace_windows
        assert wrapper.surfaceHost.instance(EDITOR) is original
        assert original.host is wrapper.surfaceHost
        assert not source.surfaceHost.contains(EDITOR)
    finally:
        monkeypatch.setattr(source.surfaceHost, "attach", attach)
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
