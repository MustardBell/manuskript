from unittest.mock import MagicMock, call

from manuskript.panels.core import EDITOR, OUTLINE, PROJECT_ENTITIES
from manuskript.ui.workspace_selection import (
    WorkspaceSelectionController,
    WorkspaceSelectionHistory,
    WorkspaceSelectionViews,
)


def _controller():
    outline_tree = MagicMock()
    project_tree = MagicMock()
    actions = tuple(MagicMock() for _ in range(5))
    views = WorkspaceSelectionViews(
        organize_action=MagicMock(),
        editor_actions=actions,
        resolve_surface=MagicMock(return_value=""),
        surface_focused=MagicMock(),
        outline_tree=outline_tree,
        project_tree=project_tree,
    )
    runtime = MagicMock()
    history = MagicMock()
    recorders = {"plugin.surface": MagicMock()}
    controller = WorkspaceSelectionController(
        views, runtime, history, recorders,
    )
    return controller, views, runtime, history, recorders


def test_regular_panel_records_identity_and_disables_editor_actions():
    controller, views, _runtime, history, _recorders = _controller()

    controller.surface_changed(PROJECT_ENTITIES)

    history.record_location.assert_called_once_with(
        ("panel", PROJECT_ENTITIES)
    )
    views.organize_action.setEnabled.assert_called_once_with(False)
    for action in views.editor_actions:
        action.setEnabled.assert_called_once_with(False)


def test_contributed_surface_delegates_to_its_recorder():
    controller, _views, _runtime, history, recorders = _controller()

    controller.surface_changed("plugin.surface")

    recorders["plugin.surface"].assert_called_once_with()
    history.record_location.assert_not_called()


def test_editor_surface_records_document_and_enables_commands():
    controller, views, runtime, history, _recorders = _controller()
    index = views.project_tree.selectionModel().currentIndex()
    index.isValid.return_value = True
    runtime.models.outline.ID.return_value = "scene-7"

    controller.surface_changed(EDITOR)

    history.record_location.assert_called_once_with(
        ("redac", "scene-7"), replace_next=True,
    )
    views.organize_action.setEnabled.assert_called_once_with(True)
    for action in views.editor_actions:
        action.setEnabled.assert_called_once_with(True)


def test_stable_selection_replaces_a_transient_empty_selection():
    controller, views, runtime, history, _recorders = _controller()
    selection = views.outline_tree.selectionModel()
    empty = MagicMock()
    empty.isValid.return_value = False
    selected = MagicMock()
    selected.isValid.return_value = True
    selection.currentIndex.side_effect = [empty, selected]
    runtime.models.outline.ID.return_value = "chapter-2"

    controller.outline_selection_changed()
    controller.outline_selection_changed()

    assert history.record_selection.call_args_list == [
        call(("outline", None), selection_empty=True),
        call(("outline", "chapter-2"), selection_empty=False),
    ]


def test_surface_event_is_replaced_by_its_immediate_tree_event():
    controller, views, runtime, history, _recorders = _controller()
    index = views.outline_tree.selectionModel().currentIndex()
    index.isValid.return_value = True
    runtime.models.outline.ID.return_value = "chapter-4"

    controller.surface_changed(OUTLINE)
    controller.outline_selection_changed()

    history.record_location.assert_called_once_with(
        ("outline", "chapter-4"), replace_next=True,
    )
    history.record_selection.assert_called_once_with(
        ("outline", "chapter-4"), selection_empty=False,
    )


def test_focus_enables_editor_actions_only_inside_editor_surface():
    controller, views, _runtime, _history, _recorders = _controller()
    child = MagicMock()
    views.resolve_surface.return_value = EDITOR

    controller.focus_changed(None, child)

    views.organize_action.setEnabled.assert_called_once_with(True)
    views.surface_focused.assert_called_once_with(EDITOR)


def test_dispose_releases_workspace_views_and_collaborators():
    controller, _views, _runtime, _navigation, recorders = _controller()

    controller.dispose()

    assert controller._views is None
    assert controller._runtime is None
    assert controller._history is None
    assert controller._surface_recorders == {}
    assert recorders


def test_workspace_history_replaces_only_after_a_transient_empty_entry():
    navigation = MagicMock()
    history = WorkspaceSelectionHistory(navigation)

    history.record_location(("panel", PROJECT_ENTITIES))
    history.record_selection(("outline", None), selection_empty=True)
    history.record_selection(("outline", "chapter-2"), selection_empty=False)

    assert navigation.record.call_args_list == [
        call(("panel", PROJECT_ENTITIES), replace=True),
        call(("outline", None), replace=False),
        call(("outline", "chapter-2"), replace=True),
    ]


def test_workspace_history_reset_resets_policy_and_navigation():
    navigation = MagicMock()
    history = WorkspaceSelectionHistory(navigation)
    history.record_selection(("outline", None), selection_empty=True)

    history.reset()
    history.record_location(("panel", PROJECT_ENTITIES))

    navigation.reset.assert_called_once_with()
    assert navigation.record.call_args_list[-1] == call(
        ("panel", PROJECT_ENTITIES), replace=True,
    )


def test_real_workspace_panel_and_outline_signals_use_controller(
    MWEmptyProject,
):
    from PyQt5.QtWidgets import qApp

    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    history = window.navigationController.history
    window.selectionHistory.reset()

    window.activatePanel(PROJECT_ENTITIES)
    qApp.processEvents()
    assert not window.menuOrganize.menuAction().isEnabled()

    item = outlineItem(title="Navigation smoke", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.corePanels.outline.treeOutlineOutline.setCurrentIndex(index)
    window.activatePanel(OUTLINE)
    qApp.processEvents()

    assert history._entries[-1] == ("outline", item.ID())
    assert not window.actCut.isEnabled()

    window.activatePanel(EDITOR)
    qApp.processEvents()
    assert window.menuOrganize.menuAction().isEnabled()
    assert window.actCut.isEnabled()
