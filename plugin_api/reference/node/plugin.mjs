#!/usr/bin/env node
import process from "node:process";

const PLUGIN_ID = "org.manuskript.reference.node";
let buffer = Buffer.alloc(0);

function declaration() {
  return {
    $kind: "record",
    name: "contribution_declaration",
    version: 1,
    fields: {
      kind: {$kind: "enum", name: "contribution_kind", value: "command"},
      descriptor: {
        $kind: "record",
        name: "extension_descriptor",
        version: 1,
        fields: {
          id: `${PLUGIN_ID}.command`,
          name: "Node.js conformance command",
          description: "",
          icon: "",
          extensions: {$kind: "tuple", items: []},
        },
      },
      configuration: {$kind: "map", items: {}},
    },
  };
}

function send(message) {
  const payload = Buffer.from(JSON.stringify(message), "utf8");
  process.stdout.write(Buffer.concat([
    Buffer.from(`Content-Length: ${payload.length}\r\n\r\n`, "ascii"),
    payload,
  ]));
}

function dispatch(message) {
  let result;
  switch (message.method) {
    case "initialize":
      result = {
        plugin_id: PLUGIN_ID,
        api_version: 1,
        protocol_version: 1,
        contributions: [{declaration: declaration(), operations: ["invoke"]}],
      };
      break;
    case "contribution/call":
      result = {$kind: "map", items: {
        language: "node",
        message: "Manuskript API 1",
      }};
      break;
    case "deactivate":
    case "shutdown":
      result = null;
      break;
    case "exit":
      process.exit(0);
      return;
    default:
      return;
  }
  if (Object.hasOwn(message, "id")) {
    send({jsonrpc: "2.0", id: message.id, result});
  }
}

function parse() {
  while (true) {
    const boundary = buffer.indexOf("\r\n\r\n");
    if (boundary < 0) return;
    const header = buffer.subarray(0, boundary).toString("ascii");
    const match = /^Content-Length:\s*(\d+)\s*$/im.exec(header);
    if (!match) process.exit(2);
    const length = Number(match[1]);
    const end = boundary + 4 + length;
    if (buffer.length < end) return;
    const payload = buffer.subarray(boundary + 4, end).toString("utf8");
    buffer = buffer.subarray(end);
    dispatch(JSON.parse(payload));
  }
}

process.stdin.on("data", chunk => {
  buffer = Buffer.concat([buffer, chunk]);
  parse();
});
