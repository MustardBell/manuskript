import json

import pytest

from manuskript.plugins.errors import PluginProtocolError
from manuskript.plugins.rpc import (
    ContentLengthParser,
    RpcLimits,
    frame_message,
)


def test_unicode_frame_survives_every_possible_chunk_boundary():
    expected = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": "Миша 🪶",
    }
    framed = frame_message(expected)
    parser = ContentLengthParser()
    messages = []

    for byte in framed:
        messages.extend(parser.feed(bytes((byte,))))

    parser.finish()
    assert messages == [expected]


def test_parser_returns_multiple_complete_messages_from_one_chunk():
    messages = [
        {"jsonrpc": "2.0", "id": 1, "result": True},
        {"jsonrpc": "2.0", "method": "changed", "params": [1, 2]},
    ]

    assert ContentLengthParser().feed(
        b"".join(frame_message(message) for message in messages)
    ) == messages


@pytest.mark.parametrize(
    "header, message",
    [
        (b"Other: 2\r\n\r\n{}", "exactly one Content-Length"),
        (
            b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
            "exactly one Content-Length",
        ),
        (b"Content-Length: nope\r\n\r\n{}", "decimal integer"),
        (b"Content-Length 2\r\n\r\n{}", "Malformed"),
    ],
)
def test_parser_rejects_malformed_headers(header, message):
    with pytest.raises(PluginProtocolError, match=message):
        ContentLengthParser().feed(header)


def test_parser_rejects_oversized_headers_and_announced_payloads():
    limits = RpcLimits(max_header_bytes=20, max_message_bytes=10)

    with pytest.raises(PluginProtocolError, match="header exceeds"):
        ContentLengthParser(limits).feed(b"X" * 21)
    with pytest.raises(PluginProtocolError, match="payload exceeds"):
        ContentLengthParser(limits).feed(
            b"Content-Length: 11\r\n\r\n"
        )


@pytest.mark.parametrize("payload", [b"{bad}", b"NaN", b"[]"])
def test_parser_rejects_non_object_or_non_json_payloads(payload):
    frame = (
        "Content-Length: {}\r\n\r\n".format(len(payload)).encode("ascii")
        + payload
    )

    with pytest.raises(PluginProtocolError):
        ContentLengthParser().feed(frame)


def test_parser_rejects_an_incomplete_final_frame():
    parser = ContentLengthParser()
    parser.feed(b"Content-Length: 20\r\n\r\n{}")

    with pytest.raises(PluginProtocolError, match="incomplete"):
        parser.finish()


def test_frame_writer_rejects_nonfinite_or_oversized_json():
    with pytest.raises(PluginProtocolError, match="finite JSON"):
        frame_message({"value": float("nan")})
    with pytest.raises(PluginProtocolError, match="payload exceeds"):
        frame_message(
            {"value": "too long"},
            RpcLimits(max_message_bytes=5),
        )


def test_frame_content_length_counts_utf8_bytes_not_characters():
    message = {"value": "ї"}
    frame = frame_message(message)
    header, payload = frame.split(b"\r\n\r\n", 1)

    assert header == "Content-Length: {}".format(
        len(payload)
    ).encode("ascii")
    assert json.loads(payload.decode("utf-8")) == message
