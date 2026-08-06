"""Which windows count as workspaces.

Only workspace windows register. That absence is how a tool window is
recognised: it neither keeps a project open nor answers for the last
close, without anything having to enumerate what "auxiliary" means.
"""

from unittest.mock import MagicMock

from manuskript.services.window_registry import WindowRegistry


def test_windows_are_kept_in_the_order_they_opened():
    registry = WindowRegistry()
    first, second = MagicMock(), MagicMock()

    registry.register(first)
    registry.register(second)

    assert registry.workspace_windows == (first, second)


def test_registering_twice_does_not_double_a_window():
    registry = WindowRegistry()
    window = MagicMock()

    registry.register(window)
    registry.register(window)

    assert registry.workspace_windows == (window,)


def test_the_only_window_is_the_last_one():
    registry = WindowRegistry()
    window = MagicMock()
    registry.register(window)

    assert registry.is_last(window)

    registry.register(MagicMock())

    assert not registry.is_last(window)


def test_a_window_that_never_registered_answers_as_last():
    """A tool window is not part of a set, so closing it is the whole of
    whatever it belongs to -- and it must never be treated as one view
    of a project among several.
    """
    registry = WindowRegistry()
    registry.register(MagicMock())

    assert registry.is_last(MagicMock())


def test_the_active_window_follows_registration_and_departure():
    registry = WindowRegistry()
    first, second = MagicMock(), MagicMock()
    registry.register(first)
    registry.register(second)

    assert registry.active is first

    registry.activate(second)
    assert registry.active is second

    registry.unregister(second)
    assert registry.active is first

    registry.unregister(first)
    assert registry.active is None


def test_activating_a_stranger_changes_nothing():
    registry = WindowRegistry()
    window = MagicMock()
    registry.register(window)

    registry.activate(MagicMock())

    assert registry.active is window


def test_focus_in_a_workspace_makes_it_active_and_is_forwarded():
    registry = WindowRegistry()
    first, second = MagicMock(), MagicMock()
    registry.register(first)
    registry.register(second)
    widget = MagicMock()
    widget.window.return_value = second

    registry.focus_changed(None, widget)

    assert registry.active is second
    second.focusChanged.assert_called_once_with(None, widget)
    first.focusChanged.assert_not_called()


def test_focus_outside_any_workspace_is_ignored():
    """A dialog or tool window gaining focus must not change which
    workspace commands are routed to.
    """
    registry = WindowRegistry()
    window = MagicMock()
    registry.register(window)
    stray = MagicMock()
    stray.window.return_value = MagicMock()

    registry.focus_changed(None, stray)
    registry.focus_changed(None, None)

    assert registry.active is window
    window.focusChanged.assert_not_called()


def test_focus_is_watched_once_however_many_windows_ask():
    """Every window asks; connecting per window would have each of them
    react to every other window's focus changes.

    The focus source is injected rather than patched onto the real
    application: replacing qApp leaves the running one unconnected and
    every binding after it wrong.
    """
    source = MagicMock()
    registry = WindowRegistry(focus_source=source)

    registry.watch_focus()
    registry.watch_focus()

    source.focusChanged.connect.assert_called_once_with(
        registry.focus_changed
    )


def test_close_all_reports_success_when_every_window_goes():
    registry = WindowRegistry()
    for _ in range(3):
        window = MagicMock()
        window.isVisible.return_value = False
        registry.register(window)

    assert registry.close_all() is True


def test_close_all_on_an_empty_registry_succeeds():
    assert WindowRegistry().close_all() is True


def test_cancelling_a_quit_leaves_every_window_open():
    """The reported defect. The save prompt used to come from whichever
    window turned out to be last, so the others were already shut when the
    person pressed Cancel -- a cancelled quit that had closed most of the
    application.
    """
    registry = WindowRegistry()
    windows = []
    for _ in range(3):
        window = MagicMock()
        window.isVisible.return_value = True
        registry.register(window)
        windows.append(window)
    # The project refuses: the person cancelled.
    windows[0].projectManager.settleBeforeClosing.return_value = False

    assert registry.close_all() is False

    for window in windows:
        window.close.assert_not_called()
    assert registry.workspace_windows == tuple(windows)


def test_a_quit_asks_about_unsaved_changes_once():
    """Three windows are three views of one project, so there is one
    question. It used to be asked by the last window to close, which is why
    the others had to be gone before it could be asked at all.
    """
    registry = WindowRegistry()
    windows = []
    for _ in range(3):
        window = MagicMock()
        window.isVisible.return_value = False
        registry.register(window)
        windows.append(window)
    windows[0].projectManager.settleBeforeClosing.return_value = True

    assert registry.close_all() is True

    windows[0].projectManager.settleBeforeClosing.assert_called_once_with()
    for window in windows[1:]:
        window.projectManager.settleBeforeClosing.assert_not_called()
    for window in windows:
        window.close.assert_called_once_with()


def test_the_project_is_settled_before_any_window_is_closed():
    """Settling after a close would be the defect with extra steps."""
    registry = WindowRegistry()
    order = []
    windows = []
    for number in range(2):
        window = MagicMock()
        window.isVisible.return_value = False
        window.close.side_effect = (
            lambda number=number: order.append("close%d" % number)
        )
        registry.register(window)
        windows.append(window)
    windows[0].projectManager.settleBeforeClosing.side_effect = (
        lambda: order.append("settle") or True
    )

    assert registry.close_all() is True

    assert order[0] == "settle"
    assert order[1:] == ["close1", "close0"]


def test_a_quit_with_no_project_manager_still_closes():
    """A window that never opened a project has nothing to settle."""
    registry = WindowRegistry()
    window = MagicMock(spec=["close", "isVisible"])
    window.isVisible.return_value = False
    registry.register(window)

    assert registry.close_all() is True
    window.close.assert_called_once_with()
