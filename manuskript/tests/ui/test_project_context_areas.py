"""Each area of the interface is bound by something that sees only it.

One class bound all four areas from one flat set of twenty-one views. Every
line of it could reach every view, so search and the metadata panel were as
close as two attributes of the same object; nothing but attention kept them
apart. Splitting it is only worth something if the separation is checked,
so this reads the modules and says what each is allowed to have heard of.

The check is over identifiers in the syntax tree, not the text, so prose
explaining why an area does not touch another area does not count as
touching it.
"""

import ast
import inspect

from manuskript.ui import project_context_binding
from manuskript.ui.project_contexts import editors, metadata
from manuskript.ui.project_contexts import reference_panels, search


def identifiers(module):
    """Every name, attribute and argument a module's code uses."""
    tree = ast.parse(inspect.getsource(module))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            found.add(node.arg)
    return found


#: The views that belong to each area. A module may name its own and must
#: not name anyone else's.
#:
#: ``text_editor_context`` is deliberately not among the editors': the
#: coordinator holds one too, because it is shared. It is the shared object
#: rather than a view of one area.
AREA_VIEWS = {
    "editors": {
        "project_tree",
        "treeOutlineOutline",
        "bind_project_model",
        "unbind_project_model",
    },
    "metadata": {"outlineItemEditor", "page_types"},
    "reference_panels": {"storyline", "cheat_sheet", "MDEditCompleter"},
    "search": {"result_views", "clearContext"},
}

MODULES = {
    "editors": editors,
    "metadata": metadata,
    "reference_panels": reference_panels,
    "search": search,
}


def test_no_area_can_name_another_areas_views():
    for name, module in MODULES.items():
        used = identifiers(module)
        for other, views in AREA_VIEWS.items():
            if other == name:
                continue
            trespass = used & views
            assert trespass == set(), (
                "{} names {}'s views: {}".format(
                    name, other, ", ".join(sorted(trespass))
                )
            )


def test_every_area_does_name_its_own_views():
    """The other half of the check: an area that named nothing of its own
    would pass the test above by doing nothing at all.
    """
    for name, module in MODULES.items():
        used = identifiers(module)
        assert used & AREA_VIEWS[name], name


def test_the_coordinator_names_no_widget_at_all():
    """What spans the areas is the reference service, the text editor
    context and the order. Not one widget: the old binding named every
    view in the set, which is what made it the place where anything to do
    with a project ended up.
    """
    used = identifiers(project_context_binding)

    every_view = set().union(*AREA_VIEWS.values())
    assert used & every_view == set(), sorted(used & every_view)


def test_no_area_reaches_for_a_window():
    """A window that answers any question is a service locator. The
    binding was the largest user of that, and splitting it must not have
    given four smaller ones a way back to it.
    """
    for name, module in MODULES.items():
        named = {
            identifier
            for identifier in identifiers(module)
            if "window" in identifier.lower()
        }
        assert named == set(), (name, sorted(named))
