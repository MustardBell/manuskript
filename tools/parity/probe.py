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

#: The three native writing surfaces whose geometry has to agree.  The
#: entity surfaces intentionally changed product shape; General, Outline and
#: Editor are the stable path a reader uses to judge the window itself.
SURFACES_TO_VISIT = (
    ("general", "txtGeneralTitle"),
    ("outline", "treeOutlineOutline"),
    ("editor", "mainEditor"),
)

#: The navigator, and the central mode container it used to drive.
NAVIGATOR = "lstTabs"
CENTRAL_STACK = "tabMain"

#: Both windows are measured at one size, or every geometry differs for a
#: reason that has nothing to do with either.
WINDOW_SIZE = (1280, 800)

#: Geometry is reported in raw pixels. Both windows run on one machine, one
#: Qt, one font set and one fixed size, so the numbers are comparable -- and
#: the tolerance for a difference nobody can see belongs in the comparator,
#: stated, rather than hidden inside a rounding step here. Whole percent was
#: about thirteen pixels at this width, which can hide a moved pane boundary.


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
    dock = window.findChild(_qt().QDockWidget, "dckNavigation")
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
        # The outer rectangle, not its title-bar implementation. Upstream
        # hides that title while this fork deliberately gives every dock the
        # distinguishable chrome the user requested; both must still reserve
        # the same part of the writing frame.
        "where": _where(window, dock) if dock is not None else None,
        "rows": rows,
    }


def _second_selector(window):
    """Whether anything other than the navigator selects a mode.

    Upstream hides the central tab bar and drives the stack from the list,
    so a visible second selector would be a difference a reader can see.
    """

    stack = window.findChild(_qt().QTabWidget, CENTRAL_STACK)
    if stack is None:
        return {"visible": False}
    bar = stack.tabBar()
    if bar is None or not bar.isVisible():
        # A hidden selector is not a second way to choose a mode, however
        # many pages it has behind it. Page counts and existence are
        # method, and belong in the diagnostics.
        return {"visible": False}
    return {"visible": True, "where": _where(window, bar)}


def _where(window, widget):
    """Where a widget sits in the window, in pixels from its top left."""

    top_left = widget.mapTo(window, widget.rect().topLeft())
    size = widget.size()
    return {
        "x": top_left.x(),
        "y": top_left.y(),
        "width": size.width(),
        "height": size.height(),
    }


def _actually_visible(window, widget):
    """Whether any part of a widget is painted inside the window.

    Qt keeps inactive tabified docks ``isVisible()`` while parking their
    native containers far outside the window.  That is useful internal
    state, but a reader sees no widget there.  Effective visibility therefore
    requires both Qt visibility and an on-window rectangle.
    """

    if widget is None or not widget.isVisible():
        return False
    top_left = widget.mapTo(window, widget.rect().topLeft())
    size = widget.size()
    return (
        top_left.x() < window.width()
        and top_left.y() < window.height()
        and top_left.x() + size.width() > 0
        and top_left.y() + size.height() > 0
    )


def _surfaces(window):
    found = {}
    for surface, name in LANDMARKS:
        widget = window.findChild(_qt().QWidget, name)
        # A widget that was never built and one sitting on a page nobody
        # selected look identical to a reader, so they answer identically
        # here. Reporting "present: false" for one of them left existence
        # in the verdict through the back door -- visible in one direction
        # only, which is worse than leaving it in openly. Whether a surface
        # *appears* when its row is chosen is the navigation question, and
        # it is asked separately.
        visible = _actually_visible(window, widget)
        if surface == "project-tree":
            # It changed from an embedded Editor child to a declared tool
            # dock. Visibility remains a parity requirement -- it must not
            # leak into General or Outline -- while its title-bar inset is
            # the intentional, user-requested distinction. The Editor's own
            # rectangle catches any wrong tree width or placement.
            found[surface] = {"visible": visible}
        else:
            found[surface] = {
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
            found[surface] = {"present": False}
            continue
        names, classes = _ancestry(widget)
        found[surface] = {
            "present": True,
            "docked": _in_a_dock(widget),
            "ancestor_names": names,
            "ancestor_classes": classes,
        }
    return found


def _visible_docks(window):
    """Docks a reader can see, and where they are.

    Only the visible ones. An inventory of every dock including the hidden
    ones puts zero pixels on screen and still fails a comparison, which is
    method wearing a verdict's clothes -- and this fork has docks upstream
    has no equivalent for, all of them hidden at first open.
    """

    docks = []
    for dock in window.findChildren(_qt().QDockWidget):
        if dock.parent() is not window or not dock.isVisible():
            continue
        docks.append({
            "title": dock.windowTitle(),
            "floating": dock.isFloating(),
            "where": _where(window, dock),
        })
    return sorted(docks, key=lambda entry: entry["title"])


def _dock_inventory(window):
    """Every dock, shown or not. Diagnostic, never a verdict."""

    found = []
    for dock in window.findChildren(_qt().QDockWidget):
        if dock.parent() is not window:
            continue
        found.append({
            "name": dock.objectName(),
            "title": dock.windowTitle(),
            "visible": dock.isVisible(),
            "floating": dock.isFloating(),
        })
    return sorted(found, key=lambda entry: entry["name"])


def _settle(app):
    for _turn in range(4):
        app.processEvents()


def _capture(window, state):
    """Optionally retain the frame behind a measurement for human review."""

    root = os.environ.get("MANUSKRIPT_PARITY_SCREENSHOTS")
    if not root:
        return
    destination = pathlib.Path(root) / pathlib.Path.cwd().name
    destination.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(destination / "{}.png".format(state)))


def _navigate_to_landmark(window, app, object_name):
    """Choose the navigator row whose surface exposes ``object_name``.

    Row numbers and translated labels are both unstable across the two
    versions.  What the row reveals is the shared fact, so discover it by
    exercising the real navigator rather than encoding either implementation's
    table in the oracle.
    """

    listing = window.findChild(_qt().QListWidget, NAVIGATOR)
    if listing is None:
        raise RuntimeError("The running window has no navigator.")
    for row in range(listing.count()):
        if listing.item(row).isHidden():
            continue
        listing.setCurrentRow(row)
        _settle(app)
        landmark = window.findChild(_qt().QWidget, object_name)
        if landmark is not None and landmark.isVisible():
            return row
    raise RuntimeError(
        "No navigator row revealed {!r}.".format(object_name)
    )


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
        ("projectManager.loadProject", ("projectManager", "loadProject")),
        ("loadProject", ("loadProject",)),
    )
    for name, attributes in routes:
        target = window
        for attribute in attributes:
            target = getattr(target, attribute, None)
            if target is None:
                break
        if target is None:
            continue
        # Called outside the existence check on purpose. Wrapping the call
        # in "except AttributeError" would read a loader that is merely
        # broken as one that is absent, and quietly fall through to the
        # older route -- a probe agreeing with itself about which version
        # it is looking at.
        target(path)
        return name
    raise RuntimeError("No way to open a project in this version.")


def describe(window, opened_by, app):
    """What a reader sees, and separately, how it was built.

    Two subtrees rather than a flat record with an ignore list. The
    comparator compares ``visual`` and nothing else, so a diagnostic added
    later cannot become part of the verdict by somebody forgetting to
    exclude it -- which is exactly what happened: the first version
    documented parentage as ignored while the comparator's default ignored
    only one field, and the twenty differences reported required a flag
    nobody would know to pass.
    """

    # Record the untouched frame before the navigation probe changes
    # anything.  A sequence that begins by selecting General can otherwise
    # hide a first-paint regression behind the very interaction intended to
    # inspect it.
    states = {
        "first-open": {
            "selected_row": _navigator_rows(window).get("current"),
            "navigator": _navigator_rows(window),
            "second_selector": _second_selector(window),
            "surfaces": _surfaces(window),
        },
    }
    _capture(window, "first-open")
    for surface, object_name in SURFACES_TO_VISIT:
        selected_row = _navigate_to_landmark(window, app, object_name)
        states[surface] = {
            "selected_row": selected_row,
            "navigator": _navigator_rows(window),
            "second_selector": _second_selector(window),
            "surfaces": _surfaces(window),
        }
        _capture(window, surface)
    return {
        "visual": {"states": states},
        "diagnostic": {
            "opened_by": opened_by,
            "method": _method(window),
            "visible_docks": _visible_docks(window),
            "dock_inventory": _dock_inventory(window),
        },
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
    _settle(app)

    description = describe(window, opened_by, app)
    if not window.close():
        raise RuntimeError("The parity window refused deterministic teardown.")
    window.deleteLater()
    from PyQt5.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _settle(app)

    json.dump(description, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
