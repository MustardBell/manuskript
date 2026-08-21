"""Describe a running Manuskript window in terms both versions can answer.

Run inside a checkout; it prints JSON on stdout. The point is to run the
same probe against upstream and against this fork and compare the two, so
that "first open looks like upstream" is settled by *running upstream*
rather than by a list of assertions somebody wrote from memory. Twice in
this work a test agreed with the implementation because it was written
after it.

Three rules keep it honest.

**The criterion is what a reader sees, not how it is built.** The user's
words: *"my requirement is visual similarity, not reproducing the method."*
So the verdict comes from geometry -- which landmarks are on screen, and
where in the window -- and not from parentage. Upstream keeps the project
tree inside the editor page's splitter while this fork puts it in a dock;
if a reader sees the same tree in the same place, that difference is
Manuskript's business and not theirs.

An earlier version compared ancestor chains and reported seventy
differences, nearly all of which were method. That is the wrong instrument
for the requirement: it would have failed on changes nobody can see and
passed things they can.

**Ask only what both versions can answer.** Nothing here mentions a class
this fork invented. A landmark is found by object name, which both have.

**Adapt only where the versions genuinely differ.** Opening a project is
such a place: upstream and this fork consume the command-line project by
different routes. Everything else is asked identically, and each adapter is
named so the list of real differences stays visible instead of spreading.
"""

import json
import os
import pathlib
import sys


#: Landmarks that exist in both versions, and the surface each one stands
#: for. Object names rather than types: a name survives a widget being
#: rebuilt by a factory, and neither version has to know our descriptor ids.
LANDMARKS = (
    ("general", "txtGeneralTitle"),
    ("outline", "treeOutlineOutline"),
    ("project-tree", "treeRedacWidget"),
    # The editor itself, not the container that used to hold every mode:
    # this fork removes the central widget while a project is open, so
    # tabMain answered "absent" for a reason that has nothing to do with
    # what a reader sees.
    ("editor", "mainEditor"),
)

#: The navigator, and the central mode container it used to drive.
NAVIGATOR = "lstTabs"
CENTRAL_STACK = "tabMain"

#: Both windows are measured at one size, or every geometry differs for a
#: reason that has nothing to do with either.
WINDOW_SIZE = (1280, 800)

#: Positions are reported in whole percent of the window. A reader notices
#: a panel on the wrong side; they do not notice four pixels, and comparing
#: exact pixels would fail on a font metric.
GRID = 100


def _ancestry(widget):
    """Every object name up from a widget, plus the classes on the way.

    The chain is what says whether a surface is docked or central, without
    either version needing to agree on what a surface is.
    """

    names, classes = [], []
    node = widget
    while node is not None:
        name = node.objectName()
        if name:
            names.append(name)
        classes.append(type(node).__name__)
        node = node.parent()
    return names, classes


def _in_a_dock(widget):
    _names, classes = _ancestry(widget)
    return "QDockWidget" in classes


def _navigator_rows(window):
    listing = window.findChild(_qt().QListWidget, NAVIGATOR)
    if listing is None:
        return {"present": False, "rows": []}
    rows = []
    for index in range(listing.count()):
        item = listing.item(index)
        rows.append({
            "row": index,
            "label": item.text() or item.toolTip(),
            "hidden": item.isHidden(),
        })
    return {
        "present": True,
        "current": listing.currentRow(),
        "rows": rows,
    }


def _second_selector(window):
    """Whether anything other than the navigator selects a mode.

    Upstream hides the central tab bar and drives the stack from the list,
    so a visible second selector would be a difference a reader can see.
    """

    stack = window.findChild(_qt().QTabWidget, CENTRAL_STACK)
    if stack is None:
        return {"present": False}
    bar = stack.tabBar()
    return {
        "present": True,
        "tab_bar_visible": bool(bar is not None and bar.isVisible()),
        "count": stack.count(),
    }


def _where(window, widget):
    """Where a widget sits in the window, in percent of it.

    What a reader sees: this much of the way across, this much down, this
    big. Rounded to whole percent because a difference smaller than that is
    a font metric rather than a rearrangement.
    """

    top_left = widget.mapTo(window, widget.rect().topLeft())
    size, frame = widget.size(), window.size()
    if not frame.width() or not frame.height():
        return None

    def percent(value, total):
        return round(GRID * value / total)

    return {
        "x": percent(top_left.x(), frame.width()),
        "y": percent(top_left.y(), frame.height()),
        "width": percent(size.width(), frame.width()),
        "height": percent(size.height(), frame.height()),
    }


def _surfaces(window):
    found = {}
    for surface, name in LANDMARKS:
        widget = window.findChild(_qt().QWidget, name)
        if widget is None:
            found[surface] = {"present": False}
            continue
        visible = widget.isVisible()
        found[surface] = {
            "present": True,
            "visible": visible,
            "where": _where(window, widget) if visible else None,
        }
    return found


def _method(window):
    """How each landmark is hosted. Diagnostic, never a verdict.

    Kept because when a visible difference does appear, the first question
    is where the thing lives -- and answering it should not need a second
    run. Compared only when asked for, since the requirement is that a
    reader sees the same window, not that we built it the same way.
    """

    found = {}
    for surface, name in LANDMARKS:
        widget = window.findChild(_qt().QWidget, name)
        if widget is None:
            continue
        names, classes = _ancestry(widget)
        found[surface] = {
            "docked": _in_a_dock(widget),
            "ancestor_names": names,
            "ancestor_classes": classes,
        }
    return found


def _docks(window):
    docks = []
    for dock in window.findChildren(_qt().QDockWidget):
        if dock.parent() is not window:
            continue
        docks.append({
            "name": dock.objectName(),
            "title": dock.windowTitle(),
            "visible": dock.isVisible(),
            "floating": dock.isFloating(),
            "area": int(window.dockWidgetArea(dock)),
        })
    return sorted(docks, key=lambda entry: entry["name"])


_QT = None


def _qt():
    global _QT
    if _QT is None:
        from PyQt5 import QtWidgets
        _QT = QtWidgets
    return _QT


def open_project(window, path):
    """Open a project by whichever route this version provides.

    The one place the two versions legitimately differ, so it is the one
    place that adapts. Each route is named rather than discovered, so a
    third appearing is a change somebody makes on purpose.
    """

    routes = (
        ("projectManager.loadProject", lambda: window.projectManager.loadProject(path)),
        ("loadProject", lambda: window.loadProject(path)),
    )
    for name, route in routes:
        try:
            route()
        except AttributeError:
            continue
        return name
    raise RuntimeError("No way to open a project in this version.")


def describe(window, opened_by):
    return {
        "opened_by": opened_by,
        "navigator": _navigator_rows(window),
        "second_selector": _second_selector(window),
        "surfaces": _surfaces(window),
        "docks": _docks(window),
        "method": _method(window),
    }


def main(argv):
    if len(argv) != 2:
        print("usage: probe.py <project.msk>", file=sys.stderr)
        return 2
    project = os.path.abspath(argv[1])

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    # The checkout this probe was copied into, not whichever Manuskript
    # happens to be installed: the whole point is to run two of them.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from manuskript import main as manuskript_main

    arguments = manuskript_main.process_commandline([])
    app, window = manuskript_main.prepare(arguments, tests=True)
    opened_by = open_project(window, project)
    window.resize(*WINDOW_SIZE)
    window.show()
    for _turn in range(4):
        app.processEvents()

    json.dump(describe(window, opened_by), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
