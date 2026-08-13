import logging
import sys
import threading
import time

import pytest

from manuskript.plugins.errors import (
    PluginProcessError,
    PluginProtocolError,
    PluginRemoteError,
    PluginRequestTimeout,
)
from manuskript.plugins.rpc import RpcProcess


FIXTURE = r'''
import json
import os
import sys


def read_message():
    header = bytearray()
    while not header.endswith(b"\r\n\r\n"):
        byte = sys.stdin.buffer.read(1)
        if not byte:
            return None
        header.extend(byte)
    length = None
    for line in bytes(header[:-4]).decode("ascii").split("\r\n"):
        name, value = line.split(":", 1)
        if name.lower() == "content-length":
            length = int(value.strip())
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def send(message):
    payload = json.dumps(
        message, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    sys.stdout.buffer.write(
        ("Content-Length: %d\r\n\r\n" % len(payload)).encode("ascii")
        + payload
    )
    sys.stdout.buffer.flush()


while True:
    message = read_message()
    if message is None:
        break
    method = message.get("method")
    request_id = message.get("id")
    if method == "echo":
        send({"jsonrpc": "2.0", "id": request_id,
              "result": message.get("params")})
    elif method == "argv":
        send({"jsonrpc": "2.0", "id": request_id,
              "result": sys.argv[1:]})
    elif method == "remote-error":
        send({"jsonrpc": "2.0", "id": request_id, "error": {
            "code": 4100, "message": "deliberate", "data": {"safe": True}
        }})
    elif method == "log":
        sys.stderr.write("a bounded diagnostic\n")
        sys.stderr.flush()
        send({"jsonrpc": "2.0", "id": request_id, "result": True})
    elif method == "notify":
        send({"jsonrpc": "2.0", "method": "fixture.changed",
              "params": {"value": 3}})
        send({"jsonrpc": "2.0", "id": request_id, "result": True})
    elif method == "hang":
        pass
    elif method == "$/cancelRequest":
        send({"jsonrpc": "2.0", "method": "fixture.cancelled",
              "params": message.get("params")})
    elif method == "malformed":
        sys.stdout.buffer.write(b"this is not rpc")
        sys.stdout.buffer.flush()
        os._exit(0)
    elif method == "crash":
        os._exit(7)
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": request_id, "result": None})
    elif method == "exit":
        break
'''


def fixture_command(tmp_path, *arguments):
    script = tmp_path / "rpc_fixture.py"
    script.write_text(FIXTURE, encoding="utf-8")
    return (sys.executable, "-B", str(script), *arguments)


def process(tmp_path, *arguments, **kwargs):
    return RpcProcess(
        "example.rpc",
        fixture_command(tmp_path, *arguments),
        tmp_path,
        **kwargs,
    )


def test_process_correlates_request_and_unicode_response(tmp_path):
    rpc = process(tmp_path)
    try:
        result = rpc.request("echo", {"text": "Гуска 🪶"}, timeout=1)
        assert result == {"text": "Гуска 🪶"}
    finally:
        rpc.shutdown(timeout=0.5)

    assert not rpc.is_running


def test_command_arguments_are_literal_and_never_pass_through_a_shell(
    tmp_path,
):
    marker = tmp_path / "must-not-exist"
    argument = "$(touch {})".format(marker)
    rpc = process(tmp_path, argument)
    try:
        assert rpc.request("argv", timeout=1) == [argument]
    finally:
        rpc.shutdown(timeout=0.5)

    assert not marker.exists()


def test_remote_error_retains_stable_code_message_and_data(tmp_path):
    rpc = process(tmp_path)
    try:
        with pytest.raises(PluginRemoteError) as caught:
            rpc.request("remote-error", timeout=1)
    finally:
        rpc.shutdown(timeout=0.5)

    assert caught.value.code == 4100
    assert caught.value.message == "deliberate"
    assert caught.value.data == {"safe": True}


def test_stderr_is_captured_with_plugin_identity(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    rpc = process(tmp_path)
    try:
        assert rpc.request("log", timeout=1)
        deadline = time.monotonic() + 1
        while "bounded diagnostic" not in caplog.text:
            assert time.monotonic() < deadline
            time.sleep(0.01)
    finally:
        rpc.shutdown(timeout=0.5)

    assert "example.rpc" in caplog.text


def test_notifications_are_delivered_without_becoming_responses(tmp_path):
    received = []
    event = threading.Event()

    def notification(method, params):
        received.append((method, params))
        event.set()

    rpc = process(tmp_path, notification_handler=notification)
    try:
        assert rpc.request("notify", timeout=1)
        assert event.wait(1)
    finally:
        rpc.shutdown(timeout=0.5)

    assert received == [("fixture.changed", {"value": 3})]


def test_notification_handler_can_make_a_request_without_deadlocking_reader(
    tmp_path,
):
    received = []
    event = threading.Event()
    rpc_box = {}

    def notification(method, params):
        received.append(
            rpc_box["rpc"].request("echo", {"nested": params}, timeout=1)
        )
        event.set()

    rpc = process(tmp_path, notification_handler=notification)
    rpc_box["rpc"] = rpc
    try:
        assert rpc.request("notify", timeout=1)
        assert event.wait(1)
    finally:
        rpc.shutdown(timeout=0.5)

    assert received == [{"nested": {"value": 3}}]


def test_request_deadline_sends_cancellation_and_returns_promptly(tmp_path):
    received = []
    event = threading.Event()

    def notification(method, params):
        received.append((method, params))
        event.set()

    rpc = process(tmp_path, notification_handler=notification)
    started = time.monotonic()
    try:
        with pytest.raises(PluginRequestTimeout, match="within"):
            rpc.request("hang", timeout=0.1)
        assert time.monotonic() - started < 1
        assert event.wait(1)
    finally:
        rpc.shutdown(timeout=0.5)

    assert received[0][0] == "fixture.cancelled"
    assert received[0][1]["id"] == 1


def test_crash_releases_waiting_request_and_teardown_is_idempotent(tmp_path):
    rpc = process(tmp_path)
    with pytest.raises(PluginProcessError, match="exit|closed"):
        rpc.request("crash", timeout=1)

    rpc.terminate(timeout=0.5)
    rpc.terminate(timeout=0.5)
    assert not rpc.is_running


def test_malformed_stdout_is_a_protocol_failure_not_a_log_line(tmp_path):
    rpc = process(tmp_path)
    try:
        with pytest.raises(PluginProtocolError, match="incomplete"):
            rpc.request("malformed", timeout=1)
    finally:
        rpc.terminate(timeout=0.5)


def test_missing_executable_fails_without_creating_reader_threads(tmp_path):
    with pytest.raises(PluginProcessError, match="Cannot start"):
        RpcProcess(
            "missing.runtime",
            (str(tmp_path / "does-not-exist"),),
            tmp_path,
        )
