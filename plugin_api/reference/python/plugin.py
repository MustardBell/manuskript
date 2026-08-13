#!/usr/bin/env python3
"""Dependency-free Python reference for the API-1 command profile."""

import json
import sys


PLUGIN_ID = "org.manuskript.reference.python"


def declaration():
    return {
        "$kind": "record",
        "name": "contribution_declaration",
        "version": 1,
        "fields": {
            "kind": {
                "$kind": "enum",
                "name": "contribution_kind",
                "value": "command",
            },
            "descriptor": {
                "$kind": "record",
                "name": "extension_descriptor",
                "version": 1,
                "fields": {
                    "id": PLUGIN_ID + ".command",
                    "name": "Python conformance command",
                    "description": "",
                    "icon": "",
                    "extensions": {"$kind": "tuple", "items": []},
                },
            },
            "configuration": {"$kind": "map", "items": {}},
        },
    }


def send(message):
    payload = json.dumps(
        message, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    sys.stdout.buffer.write(
        "Content-Length: {}\r\n\r\n".format(len(payload)).encode("ascii")
        + payload
    )
    sys.stdout.buffer.flush()


def dispatch(message):
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        result = {
            "plugin_id": PLUGIN_ID,
            "api_version": 1,
            "protocol_version": 1,
            "contributions": [{
                "declaration": declaration(),
                "operations": ["invoke"],
            }],
        }
    elif method == "contribution/call":
        result = {
            "$kind": "map",
            "items": {
                "language": "python",
                "message": "Manuskript API 1",
            },
        }
    elif method in ("deactivate", "shutdown"):
        result = None
    elif method == "exit":
        return False
    else:
        return True
    if request_id is not None:
        send({"jsonrpc": "2.0", "id": request_id, "result": result})
    return True


def main():
    buffer = bytearray()
    content_length = None
    while True:
        chunk = sys.stdin.buffer.read1(4096)
        if not chunk:
            return 0
        buffer.extend(chunk)
        while True:
            if content_length is None:
                boundary = buffer.find(b"\r\n\r\n")
                if boundary < 0:
                    break
                header = bytes(buffer[:boundary]).decode("ascii")
                del buffer[:boundary + 4]
                lengths = [
                    int(line.split(":", 1)[1].strip())
                    for line in header.split("\r\n")
                    if line.split(":", 1)[0].lower() == "content-length"
                ]
                if len(lengths) != 1:
                    return 2
                content_length = lengths[0]
            if len(buffer) < content_length:
                break
            payload = bytes(buffer[:content_length])
            del buffer[:content_length]
            content_length = None
            if not dispatch(json.loads(payload.decode("utf-8"))):
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
