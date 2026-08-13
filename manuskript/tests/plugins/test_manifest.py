import json

import pytest

from manuskript.plugins.errors import PluginManifestError
from manuskript.plugins.manifest import PluginManifest
from manuskript.plugins.runtimes import ProcessRuntime


def write_manifest(tmp_path, **overrides):
    values = {
        "id": "example.writer-tools",
        "name": "Writer tools",
        "version": "1.2.3",
        "api_version": 1,
        "runtime": {
            "kind": "python",
            "module": "plugin",
            "callable": "register",
        },
        "project_formats": {"minimum": 0, "tested_through": 2},
    }
    values.update(overrides)
    root = tmp_path / "writer-tools"
    root.mkdir()
    filename = root / "plugin.json"
    filename.write_text(json.dumps(values), encoding="utf-8")
    return filename


def test_manifest_parses_stable_identity_and_python_runtime(tmp_path):
    filename = write_manifest(tmp_path)

    manifest = PluginManifest.load(filename)

    assert manifest.id == "example.writer-tools"
    assert manifest.api_version == 1
    assert manifest.runtime.module == "plugin"
    assert manifest.runtime.callable == "register"
    assert manifest.root == filename.parent.resolve()


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"id": "../escape"}, "Invalid plugin ID"),
        ({"api_version": "one"}, "must be an integer"),
        (
            {"runtime": {
                "kind": "python",
                "module": "bad-name",
                "callable": "register",
            }},
            "module is invalid",
        ),
        ({"name": ""}, "cannot be empty"),
    ],
)
def test_manifest_rejects_invalid_contracts(
        tmp_path, overrides, message):
    filename = write_manifest(tmp_path, **overrides)

    with pytest.raises(PluginManifestError, match=message):
        PluginManifest.load(filename)


def test_manifest_parses_process_runtime_as_platform_argv(tmp_path):
    filename = write_manifest(tmp_path, runtime={
        "kind": "process",
        "protocol_version": 1,
        "commands": {
            "linux": ["node", "plugin.mjs"],
            "windows": ["node.exe", "plugin.mjs"],
        },
    })

    manifest = PluginManifest.load(filename)

    assert isinstance(manifest.runtime, ProcessRuntime)
    assert manifest.runtime.protocol_version == 1
    assert manifest.runtime.commands["linux"] == ("node", "plugin.mjs")


@pytest.mark.parametrize(
    "runtime, message",
    [
        ({"kind": "unknown"}, "kind must be"),
        (
            {"kind": "python", "module": "plugin"},
            "missing callable",
        ),
        (
            {
                "kind": "process",
                "protocol_version": 1,
                "commands": {"plan9": ["plugin"]},
            },
            "unknown platforms",
        ),
    ],
)
def test_manifest_rejects_malformed_runtime_descriptors(
    tmp_path, runtime, message,
):
    filename = write_manifest(tmp_path, runtime=runtime)

    with pytest.raises(PluginManifestError, match=message):
        PluginManifest.load(filename)
