#!/usr/bin/env python3
"""Run the Manuskript API-1 command conformance profile."""

import argparse
import json
import os
import queue
import signal
import subprocess
import sys
import threading

from pathlib import Path


class ConformanceFailure(RuntimeError):
    pass


class FrameParser:
    def __init__(self, max_header, max_message):
        self.max_header = int(max_header)
        self.max_message = int(max_message)
        self.buffer = bytearray()
        self.content_length = None

    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while True:
            if self.content_length is None:
                boundary = self.buffer.find(b"\r\n\r\n")
                if boundary < 0:
                    if len(self.buffer) > self.max_header:
                        raise ConformanceFailure("RPC header exceeds the limit")
                    return messages
                if boundary > self.max_header:
                    raise ConformanceFailure("RPC header exceeds the limit")
                header = bytes(self.buffer[:boundary])
                del self.buffer[:boundary + 4]
                lengths = []
                for line in header.split(b"\r\n"):
                    if b":" not in line:
                        raise ConformanceFailure("Malformed RPC header")
                    name, value = line.split(b":", 1)
                    if name.strip().lower() == b"content-length":
                        try:
                            lengths.append(int(value.strip().decode("ascii")))
                        except (UnicodeError, ValueError) as error:
                            raise ConformanceFailure(
                                "Content-Length is not a decimal integer"
                            ) from error
                if len(lengths) != 1:
                    raise ConformanceFailure(
                        "RPC frame needs exactly one Content-Length"
                    )
                self.content_length = lengths[0]
                if not 2 <= self.content_length <= self.max_message:
                    raise ConformanceFailure("RPC payload length is out of bounds")
            if len(self.buffer) < self.content_length:
                return messages
            payload = bytes(self.buffer[:self.content_length])
            del self.buffer[:self.content_length]
            self.content_length = None
            try:
                message = json.loads(payload.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ConformanceFailure("RPC payload is not UTF-8 JSON") from error
            if not isinstance(message, dict):
                raise ConformanceFailure("RPC message is not an object")
            messages.append(message)

    def finish(self):
        if self.content_length is not None or self.buffer:
            raise ConformanceFailure("Plugin ended with an incomplete RPC frame")


class ProcessClient:
    def __init__(self, command, cwd, protocol, timeout):
        self.command = tuple(command)
        self.timeout = float(timeout)
        self.messages = queue.Queue(maxsize=32)
        self.stderr = bytearray()
        options = {
            "cwd": str(cwd),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "bufsize": 0,
            "shell": False,
        }
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        try:
            self.process = subprocess.Popen(self.command, **options)
        except OSError as error:
            raise ConformanceFailure(
                "Cannot start {!r}: {}".format(self.command[0], error)
            ) from error
        limits = protocol["limits"]
        self.parser = FrameParser(
            limits["max_header_bytes"], limits["max_message_bytes"]
        )
        self.next_id = 1
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        self.stderr_reader = threading.Thread(
            target=self._read_stderr, daemon=True
        )
        self.reader.start()
        self.stderr_reader.start()

    def _read_stdout(self):
        try:
            while True:
                chunk = self.process.stdout.read(4096)
                if not chunk:
                    break
                for message in self.parser.feed(chunk):
                    self.messages.put(message, timeout=self.timeout)
            self.parser.finish()
            self.messages.put(None, timeout=self.timeout)
        except BaseException as error:
            try:
                self.messages.put(error, timeout=self.timeout)
            except queue.Full:
                pass

    def _read_stderr(self):
        while True:
            chunk = self.process.stderr.read(4096)
            if not chunk:
                return
            room = 65536 - len(self.stderr)
            if room > 0:
                self.stderr.extend(chunk[:room])

    def _send(self, message):
        payload = json.dumps(
            message, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
        frame = (
            "Content-Length: {}\r\n\r\n".format(len(payload)).encode("ascii")
            + payload
        )
        try:
            self.process.stdin.write(frame)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as error:
            raise ConformanceFailure("Plugin closed standard input") from error

    def notify(self, method, params=None):
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        try:
            response = self.messages.get(timeout=self.timeout)
        except queue.Empty as error:
            raise ConformanceFailure(
                "Plugin timed out answering {!r}".format(method)
            ) from error
        if response is None:
            raise ConformanceFailure(
                "Plugin exited before answering {!r}".format(method)
            )
        if isinstance(response, BaseException):
            raise ConformanceFailure(str(response)) from response
        if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
            raise ConformanceFailure(
                "Plugin returned an uncorrelated JSON-RPC response"
            )
        if "error" in response:
            raise ConformanceFailure(
                "Plugin returned an error for {!r}: {!r}"
                .format(method, response["error"])
            )
        if set(response) != {"jsonrpc", "id", "result"}:
            raise ConformanceFailure("Plugin response has unexpected fields")
        return response["result"]

    def finish(self):
        try:
            returncode = self.process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired as error:
            raise ConformanceFailure("Plugin did not exit after exit notification") from error
        if returncode:
            raise ConformanceFailure(
                "Plugin exited with status {}".format(returncode)
            )

    def terminate(self):
        if self.process.poll() is not None:
            return
        try:
            if os.name == "nt":
                self.process.terminate()
            else:
                os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()

    def diagnostic(self):
        return self.stderr.decode("utf-8", errors="replace")


def load_documents():
    root = Path(__file__).resolve().parents[1] / "schema"
    with (root / "api-1.json").open("r", encoding="utf-8") as stream:
        api = json.load(stream)
    with (root / "protocol-1.json").open("r", encoding="utf-8") as stream:
        protocol = json.load(stream)
    return api, protocol


def _expect_command(result, plugin_id, api, protocol):
    expected_fields = {"plugin_id", "api_version", "protocol_version", "contributions"}
    if not isinstance(result, dict) or set(result) != expected_fields:
        raise ConformanceFailure("initialize result has the wrong fields")
    if result["plugin_id"] != plugin_id:
        raise ConformanceFailure("initialize result has the wrong plugin id")
    if result["api_version"] != api["api_version"]:
        raise ConformanceFailure("initialize result has the wrong API version")
    if result["protocol_version"] != protocol["protocol_version"]:
        raise ConformanceFailure("initialize result has the wrong protocol version")
    contributions = result["contributions"]
    if not isinstance(contributions, list) or len(contributions) != 1:
        raise ConformanceFailure("command profile requires one contribution")
    item = contributions[0]
    if not isinstance(item, dict) or set(item) != {"declaration", "operations"}:
        raise ConformanceFailure("contribution envelope has the wrong fields")
    if item["operations"] != ["invoke"]:
        raise ConformanceFailure("command contribution must expose invoke")
    declaration = item["declaration"]
    if (
        declaration.get("$kind") != "record"
        or declaration.get("name") != "contribution_declaration"
        or declaration.get("version") != api["record_version"]
    ):
        raise ConformanceFailure("command declaration is not an API-1 record")
    fields = declaration.get("fields", {})
    kind = fields.get("kind", {})
    if kind != {"$kind": "enum", "name": "contribution_kind", "value": "command"}:
        raise ConformanceFailure("contribution kind is not command")
    descriptor = fields.get("descriptor", {})
    if descriptor.get("name") != "extension_descriptor":
        raise ConformanceFailure("command descriptor is not an extension descriptor")
    contribution_id = descriptor.get("fields", {}).get("id")
    if not isinstance(contribution_id, str) or "." not in contribution_id:
        raise ConformanceFailure("command contribution id is invalid")
    return contribution_id


def run_profile(plugin_id, language, command, cwd, timeout=5.0):
    api, protocol = load_documents()
    client = ProcessClient(command, cwd, protocol, timeout)
    try:
        params = {
            "plugin": {"id": plugin_id, "version": "conformance"},
            "host": {
                "api_version": api["api_version"],
                "protocol_version": protocol["protocol_version"],
                "project_format": 2,
                "project_generation": 0,
            },
            "capabilities": {},
            "contribution_kinds": {
                name: value["portability"]
                for name, value in protocol["contributions"].items()
            },
            "value_schema": api,
        }
        contribution_id = _expect_command(
            client.request("initialize", params), plugin_id, api, protocol
        )
        client.notify("initialized")
        client.notify("project/changed", {
            "project_generation": 1,
            "project_format": 2,
        })
        result = client.request("contribution/call", {
            "contribution_id": contribution_id,
            "operation": "invoke",
            "arguments": {"$kind": "tuple", "items": []},
        })
        expected = {
            "$kind": "map",
            "items": {
                "language": language,
                "message": "Manuskript API 1",
            },
        }
        if result != expected:
            raise ConformanceFailure(
                "invoke result is not the command-profile API value"
            )
        if client.request("deactivate") is not None:
            raise ConformanceFailure("deactivate result must be null")
        if client.request("shutdown") is not None:
            raise ConformanceFailure("shutdown result must be null")
        client.notify("exit")
        client.finish()
    except BaseException as error:
        client.terminate()
        diagnostic = client.diagnostic().strip()
        if diagnostic:
            raise ConformanceFailure(
                "{}\nplugin stderr:\n{}".format(error, diagnostic)
            ) from error
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-id", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command.pop(0)
    if not command:
        parser.error("a plugin command is required after --")
    try:
        run_profile(
            args.plugin_id,
            args.language,
            command,
            Path(args.cwd).resolve(),
            args.timeout,
        )
    except ConformanceFailure as error:
        print("FAIL: {}".format(error), file=sys.stderr)
        return 1
    print("PASS: {} implements the Manuskript API-1 command profile".format(
        args.language
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
