"""A panel that cannot be built costs a line, never anybody's attention.

This was a modal dialog once, which turns a factory fault into something
that waits for a person -- and in a test run that is a hang rather than a
failure. Where to say it has two answers in a preference order, and nobody
is a legal third: a panel opened into a window with no status bar still
must not be able to stop anything.
"""

import inspect
import logging

from unittest.mock import MagicMock

from PyQt5.QtWidgets import QMainWindow

from manuskript.panels import PanelContext, ToolPanelDescriptor
from manuskript.ui.panels import host as host_module
from manuskript.ui.panels.failures import (
    DURATION,
    IMPORTANCE,
)
from manuskript.ui.panels.window_port import PanelWindow


BROKEN = ToolPanelDescriptor(id="core.notes", title="Notes")


def reporter_for(window):
    return PanelWindow.for_window(window).failures


def test_whoever_asked_for_the_panel_is_told():
    said = []
    window = QMainWindow()

    message = reporter_for(window).report(
        BROKEN,
        RuntimeError("no widget today"),
        PanelContext(show_status=lambda *args: said.append(args)),
    )

    assert said == [(message, DURATION, IMPORTANCE)]
    assert "Notes" in message
    assert "no widget today" in message
    window.close()


def test_the_window_says_it_when_the_asker_cannot():
    """Opening a panel from a menu passes no reporter of its own; the
    window it opens into has one.
    """
    window = QMainWindow()
    window.statusPresenter = MagicMock()

    message = reporter_for(window).report(
        BROKEN, RuntimeError("no widget today"), PanelContext(),
    )

    window.statusPresenter.show.assert_called_once_with(
        message, DURATION, IMPORTANCE,
    )
    window.close()


def test_the_asker_is_preferred_to_the_window():
    """It is the nearer of the two to whatever went wrong."""
    said = []
    window = QMainWindow()
    window.statusPresenter = MagicMock()

    reporter_for(window).report(
        BROKEN,
        RuntimeError("no widget today"),
        PanelContext(show_status=lambda *args: said.append(args)),
    )

    assert len(said) == 1
    window.statusPresenter.show.assert_not_called()
    window.close()


def test_nowhere_to_say_it_is_not_a_reason_to_raise():
    window = QMainWindow()

    message = reporter_for(window).report(
        BROKEN, RuntimeError("no widget today"), None,
    )

    assert "no widget today" in message
    window.close()


def test_it_is_always_written_down(caplog):
    """The status bar is a courtesy and it scrolls away. The log is where
    somebody looks afterwards.
    """
    window = QMainWindow()

    with caplog.at_level(logging.WARNING):
        reporter_for(window).report(
            BROKEN, RuntimeError("no widget today"), PanelContext(),
        )

    assert "core.notes" in caplog.text
    assert "no widget today" in caplog.text
    window.close()


def test_the_host_does_not_know_where_to_say_it():
    """It reached for a status presenter and formatted the message itself,
    which is the last thing tying it to how a window talks to a person.
    """
    source = inspect.getsource(host_module)

    for named in ("statusPresenter", "show_status", "LOGGER"):
        assert named not in source, named
