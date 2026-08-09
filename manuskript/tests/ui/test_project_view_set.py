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


def test_the_set_is_groups_rather_than_one_flat_catalog():
    """Twenty-two fields on one object meant every binding could see every
    view, and the pressure on the file was one more field per feature. What
    a window offers is now four groups, each of which is what one binding
    is handed.
    """
    import dataclasses

    names = [
        field.name for field in dataclasses.fields(ProjectViewSet)
    ]

    assert names == [
        "models",
        "navigation",
        "editors",
        "metadata",
        "reference_panels",
        "search",
    ]


def test_a_window_supplies_its_own_views(MWEmptyProject):
    window = MWEmptyProject

    views = ProjectViewSet.for_window(window)

    # This window's own views, in the group that binds each.
    assert views.editors.outline_trees == (
        window.corePanels.project_tree.tree,
        window.treeOutlineOutline,
    )
    assert views.editors.document_area is window.mainEditor
    assert views.metadata.panel is window.corePanels.metadata
    assert views.reference_panels.storyline is window.corePanels.storyline
    assert views.search.view is window.widget
    # The project's, shared by every window showing it.
    assert views.models is window.projectRuntime.models
    assert views.editors.settings is window.projectRuntime.settingsManager
    assert views.editors.undo_stack is window.projectRuntime.undoStack


def test_two_windows_name_their_own_views_over_one_project(
        MWEmptyProject):
    """Which is the question a second window makes real: two trees, two
    editors, two metadata panels, one project.
    """
    window = MWEmptyProject
    other = window.workspaceWindows.open()
    try:
        mine = ProjectViewSet.for_window(window)
        theirs = ProjectViewSet.for_window(other)

        assert mine.editors.outline_trees != theirs.editors.outline_trees
        assert (
            mine.editors.document_area is not theirs.editors.document_area
        )
        assert mine.metadata.panel is not theirs.metadata.panel
        assert (
            mine.editors.selection_changed
            is not theirs.editors.selection_changed
        )
        # And the project underneath is the one project.
        assert mine.models is theirs.models
        assert mine.editors.settings is theirs.editors.settings
        assert mine.editors.undo_stack is theirs.editors.undo_stack
    finally:
        other.close()


def test_editors_are_asked_for_freshly_each_time(MWEmptyProject):
    """Panels come and go -- one can move to another window between a
    bind and an unbind -- so the set holds a way to ask rather than a
    list captured once.
    """
    window = MWEmptyProject
    views = ProjectViewSet.for_window(window)

    first = views.editors.text_editors()
    second = views.editors.text_editors()

    assert first is not second
    assert list(first) == list(second)


def test_panel_navigation_needs_no_window():
    """Whether the selection was empty decides whether an entry replaces
    the last one, and the history has always taken that as a parameter --
    so it is passed rather than stored where both sides can reach it.
    """
    from unittest.mock import MagicMock

    from manuskript.ui.panel_services import PanelNavigation

    history = MagicMock()
    navigation = PanelNavigation(history)

    navigation.record(("character", "alice"), selection_empty=False)
    navigation.record(("character", None), selection_empty=True)

    assert history.record.call_args_list == [
        (((("character", "alice"),)), {"replace": False}),
        (((("character", None),)), {"replace": True}),
    ]
