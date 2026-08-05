"""Two windows, one project.

This is what the runtime extraction was for. A second window is another
view: it edits the same models, shares the same undo history, and its
closing is not the project's closing. Each window keeps its own
selection, its own open documents and its own panels.
"""

from manuskript.panels.core import METADATA, PROJECT_TREE


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
