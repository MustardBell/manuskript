"""What the application's top-level widgets actually are.

Written because a report about "windows" could not be acted on without it.
A reader described several Manuskript windows sharing one taskbar entry,
raising each other, and lacking minimize and maximize -- and the code has
two quite different things that look like a window on screen:

* a workspace, which is an unparented ``QMainWindow`` that registers itself
  and owns a panel host;
* a floating panel, which is a ``QDockWidget`` parented to a workspace and
  told to float. ``PanelHost.tear_off`` says so out loud: *a floating dock,
  not a window of its own*.

Qt presents the second as a utility window belonging to the first, so it has
no independent taskbar entry, no full window chrome, and no docking areas of
its own. Every symptom in that report is what an owned utility window looks
like to somebody who expected a peer.

This does not decide which it is. It reports what is there, so the diagnosis
can be checked against a running application rather than argued from the
source. Changing window flags to make a dock imitate a workspace would leave
the ownership and docking model wrong and the symptoms half-fixed, so the
inventory comes first and deliberately answers nothing.
"""

import logging
import os

from dataclasses import dataclass


LOGGER = logging.getLogger(__name__)

#: Set to anything to have the inventory written as windows are made. Off by
#: default: this is for a session where somebody is diagnosing, and a report
#: nobody asked for is noise in every other session.
DIAGNOSTIC_VARIABLE = "MANUSKRIPT_WINDOW_INVENTORY"


#: Qt's window *type* is a masked enum, not a set of independent bits, so it
#: has to be masked out and matched exactly. Testing the values as bit flags
#: reports a Tool window as "Dialog|Tool", because Tool contains Dialog's
#: bits -- which is a diagnostic quietly saying something untrue about the
#: thing it exists to describe.
_TYPE_MASK = 0x000000FF
_WINDOW_TYPES = {
    0x00000001: "Window",
    0x00000003: "Dialog",
    0x00000005: "Sheet",
    0x00000009: "Popup",
    0x0000000B: "Tool",
    0x0000000D: "ToolTip",
    0x0000000F: "SplashScreen",
    0x00000012: "SubWindow",
}

#: These really are independent bits, and they are what the report is about:
#: a window without them has no minimize or maximize for a reader to press.
#: Named rather than numbered, and read from Qt at the point of use -- the
#: numbers were written out by hand once and Minimize was given Maximize's
#: bit, so the report named the wrong button on every line.
_HINT_NAMES = (
    "WindowMinimizeButtonHint",
    "WindowMaximizeButtonHint",
    "WindowCloseButtonHint",
    "FramelessWindowHint",
)


@dataclass(frozen=True)
class WindowFact:
    """One visible top-level widget, described rather than judged."""

    kind: str
    title: str
    parent: str
    floating_dock: bool
    workspace: bool
    flags: tuple

    def __str__(self):
        return (
            "{kind} {title!r} parent={parent} floating_dock={floating} "
            "workspace={workspace} flags={flags}"
        ).format(
            kind=self.kind, title=self.title, parent=self.parent,
            floating=self.floating_dock, workspace=self.workspace,
            flags="|".join(self.flags) or "none",
        )


def _flag_names(widget):
    from PyQt5.QtCore import Qt

    value = int(widget.windowFlags())
    kind = _WINDOW_TYPES.get(
        value & _TYPE_MASK, "type-{:#x}".format(value & _TYPE_MASK)
    )
    hints = [
        name.replace("Window", "", 1)
        for name in _HINT_NAMES
        if value & int(getattr(Qt, name))
    ]
    return (kind, *hints)


def _describe(widget, workspaces):
    from PyQt5.QtWidgets import QDockWidget

    parent = widget.parent()
    return WindowFact(
        kind=type(widget).__name__,
        title=widget.windowTitle() or "",
        parent=type(parent).__name__ if parent is not None else "none",
        floating_dock=(
            isinstance(widget, QDockWidget) and widget.isFloating()
        ),
        workspace=any(widget is window for window in workspaces),
        flags=_flag_names(widget),
    )


def take_inventory(application=None, registry=None):
    """Every widget that currently looks like a window, and what it is.

    ``registry`` is the workspace registry when there is one. Membership of
    it is the distinction the whole report turns on: a workspace answers for
    the project and can host panels, and anything else on screen is a
    utility window however much it resembles one.
    """

    from PyQt5.QtWidgets import qApp

    application = application or qApp
    if application is None:
        return ()
    try:
        workspaces = tuple(getattr(registry, "workspace_windows", ()) or ())
        widgets = tuple(application.topLevelWidgets())
    except RuntimeError:
        return ()
    found = []
    for widget in widgets:
        try:
            if not widget.isVisible():
                continue
            found.append(_describe(widget, workspaces))
        except RuntimeError:
            # A wrapper over a widget Qt has already deleted. Asking it
            # anything raises, and a widget going away while being counted
            # is ordinary rather than exceptional -- this is a description
            # of a moving thing, not a transaction over it.
            continue
    return tuple(found)


def wanted():
    """Whether anybody asked for this. Nothing here runs uninvited."""

    return bool(os.environ.get(DIAGNOSTIC_VARIABLE))


def report_inventory(application=None, registry=None):
    """Write the inventory to the log, one line per window.

    Never raises, and never runs unless asked. A diagnostic that can fail is
    worse than no diagnostic: it turns "I do not know what these windows
    are" into "and now the thing that was going to tell me is broken."
    """

    if not wanted():
        return ()
    try:
        facts = take_inventory(application, registry)
    except Exception:  # a diagnostic must not be the thing that fails
        LOGGER.debug("window inventory could not be taken", exc_info=True)
        return ()
    LOGGER.info("%d visible top-level widgets", len(facts))
    for fact in facts:
        LOGGER.info("  %s", fact)
    return facts
