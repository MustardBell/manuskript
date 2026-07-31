import json

import pytest

from manuskript.plugins.errors import PluginManifestError
from manuskript.plugins.manifest import PluginManifest


def write_manifest(tmp_path, **overrides):
    values = {
        "id": "example.writer-tools",
        "name": "Writer tools",
        "version": "1.2.3",
        "api_version": 1,
        "entry_point": "plugin:register",
    }
    values.update(overrides)
    root = tmp_path / "writer-tools"
    root.mkdir()
    filename = root / "plugin.json"
    filename.write_text(json.dumps(values), encoding="utf-8")
    return filename


def test_manifest_parses_stable_identity_and_entry_point(tmp_path):
    filename = write_manifest(tmp_path)

    manifest = PluginManifest.load(filename)

    assert manifest.id == "example.writer-tools"
    assert manifest.api_version == 1
    assert manifest.entry_module == "plugin"
    assert manifest.entry_callable == "register"
    assert manifest.root == filename.parent.resolve()


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"id": "../escape"}, "Invalid plugin ID"),
        ({"api_version": "one"}, "must be an integer"),
        ({"entry_point": "plugin.register"}, "module:callable"),
        ({"name": ""}, "cannot be empty"),
    ],
)
def test_manifest_rejects_invalid_contracts(
        tmp_path, overrides, message):
    filename = write_manifest(tmp_path, **overrides)

    with pytest.raises(PluginManifestError, match=message):
        PluginManifest.load(filename)
