from unittest.mock import MagicMock, call

from manuskript.ui.workspace_selection import (
    WorkspaceSelectionController,
    WorkspaceSelectionHistory,
    WorkspaceSelectionTabs,
    WorkspaceSelectionViews,
)


def _controller(tab_index=0):
    tabs = MagicMock()
    tabs.currentIndex.return_value = tab_index
    outline_tree = MagicMock()
    project_tree = MagicMock()
    actions = tuple(MagicMock() for _ in range(5))
    views = WorkspaceSelectionViews(
        tabs=tabs,
        organize_action=MagicMock(),
        editor_actions=actions,
        outline_tree=outline_tree,
        project_tree=project_tree,
        positions=WorkspaceSelectionTabs(
            characters=2,
            plots=3,
            world=4,
            outline=5,
            editor=6,
        ),
    )
    runtime = MagicMock()
    history = MagicMock()
    recorders = {2: MagicMock(), 3: MagicMock(), 4: MagicMock()}
    controller = WorkspaceSelectionController(
        views,
        runtime,
        history,
        recorders,
    )
    return controller, views, runtime, history, recorders


def test_regular_tab_records_its_location_and_disables_editor_actions():
    controller, views, _runtime, history, _recorders = _controller(1)

    controller.tab_changed()

    history.record_location.assert_called_once_with(("main", 1))
    views.organize_action.setEnabled.assert_called_once_with(False)
    for action in views.editor_actions:
        action.setEnabled.assert_called_once_with(False)


def test_feature_tabs_delegate_to_their_selection_controller():
    controller, _views, _runtime, history, recorders = _controller(3)

    controller.tab_changed()

    recorders[3].assert_called_once_with()
    history.record_location.assert_not_called()
    history.record_selection.assert_not_called()


def test_editor_tab_records_current_document_and_enables_commands():
    controller, views, runtime, history, _recorders = _controller(6)
    index = views.project_tree.selectionModel().currentIndex()
    index.isValid.return_value = True
    runtime.models.outline.ID.return_value = "scene-7"

    controller.tab_changed()

    history.record_location.assert_called_once_with(
        ("redac", "scene-7"),
        replace_next=True,
    )
    views.organize_action.setEnabled.assert_called_once_with(True)
    for action in views.editor_actions:
        action.setEnabled.assert_called_once_with(True)


def test_stable_selection_replaces_a_transient_empty_selection():
    controller, views, runtime, history, _recorders = _controller(5)
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


def test_tab_selection_event_is_replaced_by_its_immediate_tree_event():
    controller, views, runtime, history, _recorders = _controller(5)
    index = views.outline_tree.selectionModel().currentIndex()
    index.isValid.return_value = True
    runtime.models.outline.ID.return_value = "chapter-4"

    controller.tab_changed()
    controller.outline_selection_changed()

    history.record_location.assert_called_once_with(
        ("outline", "chapter-4"),
        replace_next=True,
    )
    history.record_selection.assert_called_once_with(
        ("outline", "chapter-4"),
        selection_empty=False,
    )


def test_dispose_releases_workspace_views_and_collaborators():
    controller, _views, _runtime, _navigation, recorders = _controller()

    controller.dispose()

    assert controller._views is None
    assert controller._runtime is None
    assert controller._history is None
    assert controller._tab_recorders == {}
    assert recorders


def test_workspace_history_replaces_only_after_a_transient_empty_entry():
    navigation = MagicMock()
    history = WorkspaceSelectionHistory(navigation)

    history.record_location(("main", 1))
    history.record_selection(("outline", None), selection_empty=True)
    history.record_selection(
        ("outline", "chapter-2"),
        selection_empty=False,
    )

    assert navigation.record.call_args_list == [
        call(("main", 1), replace=True),
        call(("outline", None), replace=False),
        call(("outline", "chapter-2"), replace=True),
    ]


def test_workspace_history_reset_resets_policy_and_navigation():
    navigation = MagicMock()
    history = WorkspaceSelectionHistory(navigation)
    history.record_selection(("outline", None), selection_empty=True)

    history.reset()
    history.record_location(("main", 0))

    navigation.reset.assert_called_once_with()
    assert navigation.record.call_args_list[-1] == call(
        ("main", 0),
        replace=True,
    )


def test_real_workspace_tab_and_outline_signals_use_the_controller(
        MWEmptyProject):
    from PyQt5.QtWidgets import qApp

    from manuskript.models.outlineItem import outlineItem

    window = MWEmptyProject
    history = window.navigationController.history
    window.selectionHistory.reset()

    window.tabMain.setCurrentIndex(window.TabSummary)
    qApp.processEvents()
    assert not window.menuOrganize.menuAction().isEnabled()

    item = outlineItem(title="Navigation smoke", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    index = window.projectRuntime.models.outline.indexFromItem(item)
    window.treeOutlineOutline.setCurrentIndex(index)
    window.tabMain.setCurrentIndex(window.TabOutline)
    qApp.processEvents()

    assert history._entries[-1] == ("outline", item.ID())
    assert not window.actCut.isEnabled()

    window.tabMain.setCurrentIndex(window.TabRedac)
    qApp.processEvents()
    assert window.menuOrganize.menuAction().isEnabled()
    assert window.actCut.isEnabled()
