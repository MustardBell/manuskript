from unittest.mock import MagicMock

import pytest

from manuskript.functions.history.Signal import Signal


def test_disconnect_removes_the_named_listener_only():
    signal = Signal()
    first = MagicMock()
    second = MagicMock()
    signal.connect(first)
    signal.connect(second)

    signal.disconnect(first)
    signal.fire("event")

    first.assert_not_called()
    second.assert_called_once_with("event")


def test_listener_can_disconnect_itself_without_skipping_the_next_one():
    signal = Signal()
    second = MagicMock()

    def first(_event):
        signal.disconnect(first)

    signal.connect(first)
    signal.connect(second)

    signal.fire("event")

    second.assert_called_once_with("event")


def test_disconnecting_an_unknown_listener_is_an_error():
    signal = Signal()

    with pytest.raises(TypeError):
        signal.disconnect(MagicMock())


def test_no_argument_disconnect_keeps_the_legacy_latest_listener_behavior():
    signal = Signal()
    first = MagicMock()
    second = MagicMock()
    signal.connect(first)
    signal.connect(second)

    signal.disconnect()
    signal.fire("event")

    first.assert_called_once_with("event")
    second.assert_not_called()
