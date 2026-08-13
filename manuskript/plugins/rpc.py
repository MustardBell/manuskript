"""Bounded JSON-RPC 2.0 transport for external plugin processes."""

import json
import logging
import os
import queue
import signal
import subprocess
import threading
import time

from dataclasses import dataclass, field

from manuskript.plugins.errors import (
    PluginConflictError,
    PluginProcessError,
    PluginProtocolError,
    PluginRemoteError,
    PluginRequestTimeout,
    PluginScopeError,
)


LOGGER = logging.getLogger(__name__)
JSONRPC_VERSION = "2.0"
CANCEL_METHOD = "$/cancelRequest"


@dataclass(frozen=True)
class RpcLimits:
    max_header_bytes: int = 8192
    max_message_bytes: int = 16 * 1024 * 1024
    stderr_chunk_bytes: int = 4096
    max_pending_notifications: int = 128

    def __post_init__(self):
        if min(
            self.max_header_bytes,
            self.max_message_bytes,
            self.stderr_chunk_bytes,
            self.max_pending_notifications,
        ) < 1:
            raise ValueError("RPC limits must be positive.")


class ContentLengthParser:
    """Incrementally parse LSP-style Content-Length framed JSON objects."""

    def __init__(self, limits=None):
        self.limits = limits or RpcLimits()
        self._buffer = bytearray()
        self._content_length = None

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("RPC parser input must be bytes.")
        self._buffer.extend(data)
        messages = []
        while True:
            if self._content_length is None:
                boundary = self._buffer.find(b"\r\n\r\n")
                if boundary < 0:
                    if len(self._buffer) > self.limits.max_header_bytes:
                        raise PluginProtocolError(
                            "RPC header exceeds {} bytes."
                            .format(self.limits.max_header_bytes)
                        )
                    break
                if boundary > self.limits.max_header_bytes:
                    raise PluginProtocolError(
                        "RPC header exceeds {} bytes."
                        .format(self.limits.max_header_bytes)
                    )
                header = bytes(self._buffer[:boundary])
                del self._buffer[:boundary + 4]
                self._content_length = self._parse_header(header)

            if len(self._buffer) < self._content_length:
                break
            payload = bytes(self._buffer[:self._content_length])
            del self._buffer[:self._content_length]
            self._content_length = None
            messages.append(self._parse_payload(payload))
        return messages

    def finish(self):
        if self._content_length is not None or self._buffer:
            raise PluginProtocolError(
                "Plugin closed stdout with an incomplete RPC frame."
            )

    def _parse_header(self, header):
        try:
            text = header.decode("ascii")
        except UnicodeDecodeError as error:
            raise PluginProtocolError(
                "RPC headers must contain ASCII."
            ) from error
        lengths = []
        for line in text.split("\r\n"):
            if ":" not in line:
                raise PluginProtocolError("Malformed RPC header line.")
            name, value = line.split(":", 1)
            if name.strip().lower() == "content-length":
                value = value.strip()
                if not value.isdigit():
                    raise PluginProtocolError(
                        "RPC Content-Length must be a decimal integer."
                    )
                lengths.append(int(value))
        if len(lengths) != 1:
            raise PluginProtocolError(
                "RPC frame requires exactly one Content-Length header."
            )
        length = lengths[0]
        if length < 2:
            raise PluginProtocolError("RPC payload is too short.")
        if length > self.limits.max_message_bytes:
            raise PluginProtocolError(
                "RPC payload exceeds {} bytes."
                .format(self.limits.max_message_bytes)
            )
        return length

    @staticmethod
    def _parse_payload(payload):
        try:
            text = payload.decode("utf-8")
            value = json.loads(
                text,
                parse_constant=lambda constant: _invalid_number(constant),
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PluginProtocolError(
                "RPC payload is not valid UTF-8 JSON."
            ) from error
        if not isinstance(value, dict):
            raise PluginProtocolError(
                "RPC messages must contain a JSON object."
            )
        return value


def frame_message(message, limits=None):
    limits = limits or RpcLimits()
    if not isinstance(message, dict):
        raise PluginProtocolError("RPC messages must be JSON objects.")
    try:
        payload = json.dumps(
            message,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PluginProtocolError(
            "RPC message is not a finite JSON value."
        ) from error
    if len(payload) > limits.max_message_bytes:
        raise PluginProtocolError(
            "RPC payload exceeds {} bytes."
            .format(limits.max_message_bytes)
        )
    return (
        "Content-Length: {}\r\n\r\n".format(len(payload)).encode("ascii")
        + payload
    )


@dataclass
class _PendingRequest:
    event: threading.Event = field(default_factory=threading.Event)
    result: object = None
    error: object = None


class RpcProcess:
    """Own one plugin process and correlate its JSON-RPC requests."""

    def __init__(
        self,
        plugin_id,
        command,
        cwd,
        limits=None,
        notification_handler=None,
        request_handler=None,
        environment=None,
    ):
        if isinstance(command, str) or not command:
            raise ValueError("Plugin commands must be nonempty argv arrays.")
        if any(not isinstance(argument, str) for argument in command):
            raise ValueError("Plugin command arguments must be strings.")
        self.plugin_id = str(plugin_id)
        self.command = tuple(command)
        self.cwd = str(cwd)
        self.limits = limits or RpcLimits()
        self.notification_handler = notification_handler
        self.request_handler = request_handler
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._pending = {}
        self._next_id = 1
        self._failure = None
        self._closing = False
        self._expecting_exit = False
        self._notification_queue = (
            queue.Queue(maxsize=self.limits.max_pending_notifications)
            if notification_handler is not None
            else None
        )
        self._host_request_queue = (
            queue.Queue(maxsize=self.limits.max_pending_notifications)
            if request_handler is not None
            else None
        )

        options = {
            "cwd": self.cwd,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "bufsize": 0,
            "shell": False,
            "env": environment,
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        try:
            self.process = subprocess.Popen(self.command, **options)
        except OSError as error:
            raise PluginProcessError(
                "Cannot start plugin {}: {}".format(self.plugin_id, error)
            ) from error

        self._stdout_thread = threading.Thread(
            target=self._read_stdout,
            name="plugin-{}-rpc".format(self.plugin_id),
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="plugin-{}-stderr".format(self.plugin_id),
            daemon=True,
        )
        self._notification_thread = (
            threading.Thread(
                target=self._deliver_notifications,
                name="plugin-{}-notifications".format(self.plugin_id),
                daemon=True,
            )
            if self._notification_queue is not None
            else None
        )
        self._host_request_thread = (
            threading.Thread(
                target=self._answer_host_requests,
                name="plugin-{}-host-requests".format(self.plugin_id),
                daemon=True,
            )
            if self._host_request_queue is not None
            else None
        )
        self._stdout_thread.start()
        self._stderr_thread.start()
        if self._notification_thread is not None:
            self._notification_thread.start()
        if self._host_request_thread is not None:
            self._host_request_thread.start()

    @property
    def is_running(self):
        return self.process.poll() is None

    @property
    def failure(self):
        with self._state_lock:
            return self._failure

    def request(self, method, params=None, timeout=30.0):
        if timeout is None or timeout <= 0:
            raise ValueError("RPC request timeouts must be positive.")
        with self._state_lock:
            self._raise_failure_locked()
            if self._closing:
                raise PluginProcessError("Plugin process is closing.")
            request_id = self._next_id
            self._next_id += 1
            pending = _PendingRequest()
            self._pending[request_id] = pending
        message = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "method": _method(method),
        }
        if params is not None:
            _params(params)
            message["params"] = params
        try:
            self._write(message)
        except Exception:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise

        if not pending.event.wait(timeout):
            with self._state_lock:
                self._pending.pop(request_id, None)
            try:
                self.notify(CANCEL_METHOD, {"id": request_id})
            except PluginProcessError:
                pass
            raise PluginRequestTimeout(
                "Plugin {} did not answer {!r} within {:.3f} seconds."
                .format(self.plugin_id, method, timeout)
            )
        if pending.error is not None:
            if isinstance(pending.error, BaseException):
                raise pending.error
            error = pending.error
            raise PluginRemoteError(
                error.get("code"),
                error.get("message", "Remote error"),
                error.get("data"),
            )
        return pending.result

    def notify(self, method, params=None):
        message = {
            "jsonrpc": JSONRPC_VERSION,
            "method": _method(method),
        }
        if params is not None:
            _params(params)
            message["params"] = params
        self._write(message)

    def shutdown(self, timeout=1.0):
        """Request orderly shutdown, then terminate the process group."""
        if self.process.poll() is None and self.failure is None:
            with self._state_lock:
                self._expecting_exit = True
            try:
                self.request("shutdown", timeout=timeout)
                self.notify("exit")
            except (
                PluginProcessError,
                PluginProtocolError,
                PluginRemoteError,
            ):
                pass
        with self._state_lock:
            self._closing = True
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.terminate(timeout=timeout)
        self._close_pipes()
        self._join_readers(timeout)

    def terminate(self, timeout=1.0):
        with self._state_lock:
            self._closing = True
        self._fail(PluginProcessError(
            "Plugin {} process was terminated.".format(self.plugin_id)
        ))
        if self.process.poll() is None:
            self._signal_group(signal.SIGTERM)
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._signal_group(
                    getattr(signal, "SIGKILL", signal.SIGTERM)
                )
                try:
                    self.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    LOGGER.error(
                        "Plugin %s process did not die after kill.",
                        self.plugin_id,
                    )
        self._close_pipes()
        self._join_readers(timeout)

    def _write(self, message):
        frame = frame_message(message, self.limits)
        with self._write_lock:
            with self._state_lock:
                self._raise_failure_locked()
                if self._closing:
                    raise PluginProcessError("Plugin process is closing.")
            try:
                self.process.stdin.write(frame)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as error:
                failure = PluginProcessError(
                    "Plugin {} closed its RPC input: {}"
                    .format(self.plugin_id, error)
                )
                self._fail(failure)
                raise failure from error

    def _read_stdout(self):
        parser = ContentLengthParser(self.limits)
        try:
            while True:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                for message in parser.feed(chunk):
                    self._dispatch(message)
            parser.finish()
            if not self._closing and not self._expecting_exit:
                returncode = self.process.poll()
                if returncode is None:
                    try:
                        returncode = self.process.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        returncode = "unknown"
                self._fail(PluginProcessError(
                    "Plugin {} closed RPC output (exit {})."
                    .format(self.plugin_id, returncode)
                ))
        except PluginProtocolError as error:
            self._fail(error)
            self._terminate_from_reader()
        except Exception as error:
            failure = PluginProcessError(
                "Plugin {} RPC reader failed: {}: {}"
                .format(self.plugin_id, type(error).__name__, error)
            )
            self._fail(failure)
            self._terminate_from_reader()

    def _read_stderr(self):
        try:
            while True:
                chunk = self.process.stderr.read(self.limits.stderr_chunk_bytes)
                if not chunk:
                    return
                LOGGER.warning(
                    "Plugin %s stderr: %s",
                    self.plugin_id,
                    chunk.decode("utf-8", errors="replace").rstrip(),
                )
        except (OSError, ValueError):
            return

    def _dispatch(self, message):
        if message.get("jsonrpc") != JSONRPC_VERSION:
            raise PluginProtocolError(
                "RPC message has an unsupported jsonrpc version."
            )
        if "method" in message:
            self._dispatch_incoming(message)
            return
        if "id" not in message:
            raise PluginProtocolError(
                "RPC response requires an id."
            )
        has_result = "result" in message
        has_error = "error" in message
        if has_result == has_error:
            raise PluginProtocolError(
                "RPC response requires exactly one result or error."
            )
        request_id = message["id"]
        if isinstance(request_id, bool) or not isinstance(
            request_id, (int, str)
        ):
            raise PluginProtocolError(
                "RPC response ids must be integers or strings."
            )
        with self._state_lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            LOGGER.debug(
                "Plugin %s returned an unknown request id %r.",
                self.plugin_id,
                request_id,
            )
            return
        if has_error:
            error = message["error"]
            if (
                not isinstance(error, dict)
                or isinstance(error.get("code"), bool)
                or not isinstance(error.get("code"), int)
                or not isinstance(error.get("message"), str)
            ):
                raise PluginProtocolError(
                    "RPC error response is malformed."
                )
            pending.error = error
        else:
            pending.result = message["result"]
        pending.event.set()

    def _dispatch_incoming(self, message):
        method = message.get("method")
        if not isinstance(method, str) or not method:
            raise PluginProtocolError("RPC method names must be nonempty strings.")
        if "params" in message:
            try:
                _params(message["params"])
            except (TypeError, ValueError) as error:
                raise PluginProtocolError(str(error)) from error
        if "id" in message:
            request_id = message["id"]
            if isinstance(request_id, bool) or not isinstance(
                request_id, (int, str)
            ):
                raise PluginProtocolError(
                    "RPC request ids must be integers or strings."
                )
            if self._host_request_queue is None:
                self._write({
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Host method is not available.",
                    },
                })
                return
            try:
                self._host_request_queue.put_nowait((
                    request_id, method, message.get("params")
                ))
            except queue.Full as error:
                raise PluginProtocolError(
                    "Plugin host-request queue exceeds {} messages."
                    .format(self.limits.max_pending_notifications)
                ) from error
            return
        if self.notification_handler is not None:
            try:
                self._notification_queue.put_nowait(
                    (method, message.get("params"))
                )
            except queue.Full as error:
                raise PluginProtocolError(
                    "Plugin notification queue exceeds {} messages."
                    .format(self.limits.max_pending_notifications)
                ) from error

    def _deliver_notifications(self):
        while True:
            item = self._notification_queue.get()
            if item is None:
                return
            method, params = item
            try:
                self.notification_handler(method, params)
            except Exception:
                LOGGER.exception(
                    "Plugin %s notification handler failed for %s.",
                    self.plugin_id,
                    method,
                )

    def _answer_host_requests(self):
        while True:
            item = self._host_request_queue.get()
            if item is None:
                return
            request_id, method, params = item
            try:
                result = self.request_handler(method, params)
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "result": result,
                }
            except PluginConflictError as error:
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "error": {
                        "code": 4090,
                        "message": str(error),
                        "data": error.data,
                    },
                }
            except PluginScopeError as error:
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "error": {
                        "code": 4030,
                        "message": str(error),
                    },
                }
            except (
                PluginProtocolError,
                TypeError,
                ValueError,
                KeyError,
            ) as error:
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "error": {
                        "code": 4000,
                        "message": "{}: {}".format(
                            type(error).__name__, error
                        ),
                    },
                }
            except Exception as error:
                LOGGER.exception(
                    "Plugin %s host request %s failed.",
                    self.plugin_id,
                    method,
                )
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": request_id,
                    "error": {
                        "code": 5000,
                        "message": "Host capability operation failed.",
                    },
                }
            try:
                self._write(response)
            except PluginProcessError:
                return

    def _fail(self, error):
        with self._state_lock:
            if self._failure is None:
                self._failure = error
            pending = tuple(self._pending.values())
            self._pending.clear()
        for request in pending:
            request.error = self._failure
            request.event.set()

    def _raise_failure_locked(self):
        if self._failure is not None:
            raise self._failure
        returncode = self.process.poll()
        if returncode is not None and not self._closing:
            raise PluginProcessError(
                "Plugin {} exited with status {}."
                .format(self.plugin_id, returncode)
            )

    def _signal_group(self, signal_value):
        try:
            if os.name == "nt":
                if signal_value == signal.SIGTERM:
                    self.process.terminate()
                else:
                    self.process.kill()
            else:
                os.killpg(self.process.pid, signal_value)
        except (OSError, ProcessLookupError):
            pass

    def _terminate_from_reader(self):
        if self.process.poll() is not None:
            return
        self._signal_group(signal.SIGTERM)

    def _close_pipes(self):
        for stream in (
            self.process.stdin,
            self.process.stdout,
            self.process.stderr,
        ):
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    def _join_readers(self, timeout):
        if self._notification_queue is not None:
            try:
                self._notification_queue.put(None, timeout=max(0.0, timeout))
            except queue.Full:
                pass
        if self._host_request_queue is not None:
            try:
                self._host_request_queue.put(None, timeout=max(0.0, timeout))
            except queue.Full:
                pass
        current = threading.current_thread()
        threads = [self._stdout_thread, self._stderr_thread]
        if self._notification_thread is not None:
            threads.append(self._notification_thread)
        if self._host_request_thread is not None:
            threads.append(self._host_request_thread)
        for thread in threads:
            if thread is not current:
                thread.join(timeout=max(0.0, timeout))

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.shutdown()


def _method(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("RPC method names cannot be empty.")
    return value.strip()


def _params(value):
    if not isinstance(value, (dict, list)):
        raise TypeError("RPC params must be an object or array.")
    return value


def _invalid_number(constant):
    raise PluginProtocolError(
        "RPC JSON numbers must be finite, not {}.".format(constant)
    )
