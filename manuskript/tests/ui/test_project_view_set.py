"""One place reads a window; nothing downstream of it does.

The view set exists so that "which outline tree" and "whose selection"
are answered once, by whoever assembles it, instead of being asked of a
window by everything that needs an answer.
"""

import ast
import inspect

from manuskript.ui import project_context_binding
from manuskript.ui.project_view_set import ProjectViewSet


def window_names(module):
    """Every place a module's code names a window.

    Read from the syntax tree rather than the text, so that prose
    explaining why there is no window here does not count as one.
    """
    tree = ast.parse(inspect.getsource(module))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and "window" in node.id.lower():
            found.add(node.id)
        elif isinstance(node, ast.arg) and "window" in node.arg.lower():
            found.add(node.arg)
        elif (
            isinstance(node, ast.Attribute)
            and "window" in node.attr.lower()
        ):
            found.add(node.attr)
    return found


def test_the_binding_never_reaches_for_a_window():
    """A window that answers any question is a service locator. The
    binding was the largest user of that, and this is what stops it
    growing back.
    """
    assert window_names(project_context_binding) == set(), (
        "manuskript.ui.project_context_binding names a window again. "
        "Add what it needs to ProjectViewSet and read it from there."
    )


def test_a_window_supplies_its_own_views(MWEmptyProject):
    window = MWEmptyProject

    views = ProjectViewSet.for_window(window)

    # This window's own views.
    assert views.outline_trees == (
        window.treeRedacOutline,
        window.treeOutlineOutline,
    )
    assert views.document_area is window.mainEditor
    assert views.metadata_panel is window.redacMetadata
    assert views.storyline is window.storylineView
    assert views.search_view is window.widget
    # The project's, shared by every window showing it.
    assert views.models is window.projectRuntime.models
    assert views.settings is window.projectRuntime.settingsManager
    assert views.undo_stack is window.projectRuntime.undoStack


def test_two_windows_name_their_own_views_over_one_project(
        MWEmptyProject):
    """Which is the question a second window makes real: two trees, two
    editors, two metadata panels, one project.
    """
    window = MWEmptyProject
    other = window.openWorkspaceWindow()
    try:
        mine = ProjectViewSet.for_window(window)
        theirs = ProjectViewSet.for_window(other)

        assert mine.outline_trees != theirs.outline_trees
        assert mine.document_area is not theirs.document_area
        assert mine.metadata_panel is not theirs.metadata_panel
        assert mine.selection_changed is not theirs.selection_changed
        # And the project underneath is the one project.
        assert mine.models is theirs.models
        assert mine.settings is theirs.settings
        assert mine.undo_stack is theirs.undo_stack
    finally:
        other.close()


def test_editors_are_asked_for_freshly_each_time(MWEmptyProject):
    """Panels come and go -- one can move to another window between a
    bind and an unbind -- so the set holds a way to ask rather than a
    list captured once.
    """
    window = MWEmptyProject
    views = ProjectViewSet.for_window(window)

    first = views.text_editors()
    second = views.text_editors()

    assert first is not second
    assert list(first) == list(second)
