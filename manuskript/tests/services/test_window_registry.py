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
