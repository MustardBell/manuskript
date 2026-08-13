import json
import shutil

from pathlib import Path

import pytest

from manuskript.plugins.execution import run_export
from manuskript.plugins.runtime import PluginRuntime, PluginStatus
from manuskript.plugins.runtimes import current_platform
from manuskript.services.plugin_preferences import InMemoryPluginPreferences
from manuskript.tests.plugins.test_process_driver import (
    create_process_plugin,
    portable_contributions,
)


NODE_PLUGIN = r'''
import fs from "node:fs";

const data = JSON.parse(fs.readFileSync("fixture_data.json", "utf8"));
let buffer = Buffer.alloc(0);

function send(message) {
  const payload = Buffer.from(JSON.stringify(message), "utf8");
  process.stdout.write(
    Buffer.concat([
      Buffer.from(`Content-Length: ${payload.length}\r\n\r\n`, "ascii"),
      payload,
    ])
  );
}

function dispatch(message) {
  const method = message.method;
  if (method === "initialize") {
    send({jsonrpc: "2.0", id: message.id, result: {
      plugin_id: data.plugin_id,
      api_version: 1,
      protocol_version: 1,
      contributions: [data.contributions[0]],
    }});
  } else if (method === "contribution/call") {
    send({jsonrpc: "2.0", id: message.id, result: data.results.export});
  } else if (method === "deactivate" || method === "shutdown") {
    send({jsonrpc: "2.0", id: message.id, result: null});
  } else if (method === "exit") {
    process.exit(0);
  }
}

function parse() {
  while (true) {
    const boundary = buffer.indexOf("\r\n\r\n");
    if (boundary < 0) return;
    const header = buffer.subarray(0, boundary).toString("ascii");
    const match = /Content-Length:\s*(\d+)/i.exec(header);
    if (!match) process.exit(9);
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
'''


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_node_plugin_implements_the_same_exporter_contract(tmp_path):
    plugin_root = create_process_plugin(
        tmp_path,
        contributions=(portable_contributions()[0],),
    )
    (plugin_root / "plugin.mjs").write_text(NODE_PLUGIN, encoding="utf-8")
    manifest_path = plugin_root / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime"]["commands"] = {
        current_platform(): ["node", "plugin.mjs"]
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    runtime = PluginRuntime(
        [tmp_path],
        InMemoryPluginPreferences(["example.remote"]),
    )

    runtime.discover()
    runtime.load_enabled()
    record = runtime.records["example.remote"]
    try:
        assert record.status is PluginStatus.LOADED, record.error
        artifact = run_export(runtime.registry.exporters[0], {"book": True})
        assert artifact.content == "exported"
        assert artifact.suggested_name == "story.txt"
    finally:
        runtime.disable("example.remote")

    assert record.session is None
