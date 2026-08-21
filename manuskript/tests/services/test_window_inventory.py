"""Telling a workspace window from a floating panel that resembles one."""

import pytest

pytest.importorskip("PyQt5.QtWidgets", reason="needs Qt")

from PyQt5.QtWidgets import (  # noqa: E402
    QApplication,
    QDockWidget,
    QMainWindow,
    QWidget,
    qApp,
)

from manuskript.services.window_inventory import take_inventory  # noqa: E402


APP = QApplication.instance() or QApplication([])


class Registry:
    def __init__(self, windows=()):
        self.workspace_windows = tuple(windows)


class _Present:
    """A top-level widget that answers every question the inventory asks."""

    def __init__(self, title):
        self._title = title

    def isVisible(self):
        return True

    def windowTitle(self):
        return self._title

    def parent(self):
        return None

    def windowFlags(self):
        return 0x00000001


#: Widgets this file made, and only those. An earlier version disposed of
#: every top-level widget after each test, which in a shared process
#: destroyed the session-scoped workspace window other files depend on --
#: 180 tests that never mention windows failed because of it.
_MADE = []


def window(title):
    """A top-level window owned by this file and disposed of with it."""

    made = QMainWindow()
    made.setWindowTitle(title)
    made.show()
    qApp.processEvents()
    _MADE.append(made)
    return made


@pytest.fixture(autouse=True)
def dispose_only_what_this_file_made():
    yield
    qApp.processEvents()
    while _MADE:
        made = _MADE.pop()
        made.close()
        made.deleteLater()
    qApp.processEvents()


def test_a_floating_panel_is_reported_as_a_dock_and_not_as_a_workspace():
    """The distinction the whole window report turns on.

    A floating dock looks like a window on screen and is a utility window
    owned by its parent: no taskbar entry of its own, no full chrome, and
    no docking areas. Reading it as a peer window is what made six symptoms
    look like six problems.
    """

    workspace = window("Manuskript")
    dock = QDockWidget("Editor", workspace)
    dock.setWidget(QWidget())
    workspace.addDockWidget(1, dock)
    dock.setFloating(True)
    dock.show()
    qApp.processEvents()

    facts = {fact.title: fact for fact in take_inventory(
        qApp, Registry([workspace])
    )}

    assert facts["Manuskript"].workspace
    assert not facts["Manuskript"].floating_dock
    assert facts["Editor"].floating_dock
    assert not facts["Editor"].workspace
    assert facts["Editor"].parent == "QMainWindow"


def test_a_second_workspace_is_reported_as_one():
    """Unparented, registered, and a peer of the first."""

    first = window("first")
    second = window("second")

    facts = {fact.title: fact for fact in take_inventory(
        qApp, Registry([first, second])
    )}

    assert facts["second"].workspace
    assert facts["second"].parent == "none"
    assert not facts["second"].floating_dock


def test_a_window_nobody_registered_is_reported_as_not_a_workspace():
    """Absence from the registry is the fact, not an inference from type."""

    stray = window("stray")

    facts = {fact.title: fact for fact in take_inventory(qApp, Registry())}

    assert not facts["stray"].workspace


def test_hidden_widgets_are_left_out_because_the_report_is_about_what_is_seen():
    hidden = QMainWindow()
    hidden.setWindowTitle("hidden")
    _MADE.append(hidden)

    titles = {fact.title for fact in take_inventory(qApp, Registry())}

    assert "hidden" not in titles


def test_the_inventory_survives_having_no_registry_at_all():
    """It is a diagnostic; it must never be the thing that fails."""

    window("alone")

    facts = take_inventory(qApp, None)

    assert any(fact.title == "alone" for fact in facts)
    assert not any(fact.workspace for fact in facts)


def test_a_widget_qt_already_deleted_is_skipped_rather_than_fatal():
    """A diagnostic that can fail is worse than no diagnostic.

    Taking the inventory during a suite full of half-torn-down widgets
    raised on every wrapper over a deleted object, and 180 tests that had
    nothing to do with windows failed because the thing describing them
    did. It describes something that is moving; a widget leaving while
    being counted is ordinary.

    Asserted against a stub that raises rather than by deleting a real
    window out from under Qt. The contract is "a widget that raises is
    skipped", and provoking it for real poisons every test that runs
    afterwards -- which is how this defect was found in the first place.
    """

    class Gone:
        """What PyQt gives back for a widget Qt has already deleted."""

        def isVisible(self):
            raise RuntimeError("wrapped C/C++ object has been deleted")

    class Application:
        @staticmethod
        def topLevelWidgets():
            return [Gone(), _Present("alive")]

    facts = take_inventory(Application(), Registry())

    assert [fact.title for fact in facts] == ["alive"]


def test_nothing_is_reported_unless_somebody_asked(monkeypatch):
    """Off by default: a report nobody wanted is noise in every session."""

    from manuskript.services import window_inventory

    window("asked")

    monkeypatch.delenv(window_inventory.DIAGNOSTIC_VARIABLE, raising=False)
    assert window_inventory.report_inventory(qApp, Registry()) == ()

    monkeypatch.setenv(window_inventory.DIAGNOSTIC_VARIABLE, "1")
    assert window_inventory.report_inventory(qApp, Registry())


def test_the_registry_it_is_given_is_the_one_that_knows(monkeypatch):
    """A diagnostic that lies is worse than one that is missing.

    The first hook passed a registry that did not exist -- the placement
    target has no such attribute -- so every window came back as "not a
    workspace". That would have confirmed the theory it was built to test,
    for entirely the wrong reason.
    """

    from manuskript.services import window_inventory

    monkeypatch.setenv(window_inventory.DIAGNOSTIC_VARIABLE, "1")
    known = window("registered")

    told = window_inventory.report_inventory(qApp, Registry([known]))
    untold = window_inventory.report_inventory(qApp, None)

    assert any(fact.workspace for fact in told)
    assert not any(fact.workspace for fact in untold)


def test_a_tool_window_is_not_reported_as_a_dialog_as_well():
    """Qt's window type is a masked enum, not independent bits.

    Testing the values as bit flags said "Dialog|Tool" of every tool window,
    because Tool contains Dialog's bits -- a diagnostic saying something
    untrue about the one thing it exists to describe.
    """

    from PyQt5.QtCore import Qt

    from manuskript.services.window_inventory import _flag_names

    class Widget:
        def __init__(self, flags):
            self._flags = flags

        def windowFlags(self):
            return self._flags

    tool = _flag_names(Widget(Qt.Tool))
    dialog = _flag_names(Widget(Qt.Dialog))
    plain = _flag_names(Widget(
        Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint
    ))

    assert tool[0] == "Tool" and "Dialog" not in tool
    assert dialog[0] == "Dialog" and "Tool" not in dialog
    assert plain[0] == "Window"
    assert "MinimizeButtonHint" in plain and "CloseButtonHint" in plain
    # And a button that is not there is not named.
    assert "MaximizeButtonHint" not in plain
