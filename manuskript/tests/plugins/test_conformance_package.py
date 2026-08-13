import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from manuskript.plugins.contracts import (
    CONTRIBUTION_CONTRACTS,
    PLUGIN_API_VERSION,
    PLUGIN_PROTOCOL_VERSION,
)
from manuskript.plugins.drivers import (
    MAX_REMOTE_CONTRIBUTIONS,
    _REMOTE_OPERATIONS,
)
from manuskript.plugins.rpc import RpcLimits
from manuskript.plugins.specification import (
    api_schema_document,
    protocol_document,
)
from manuskript.plugins.values import api_value_codec


ROOT = Path(__file__).resolve().parents[3]
RUNNER = ROOT / "plugin_api" / "conformance" / "run.py"


def test_checked_in_documents_are_the_runtime_source_of_truth():
    api = api_schema_document()
    protocol = protocol_document()
    limits = RpcLimits()

    assert api_value_codec().schema_document == api
    assert api["api_version"] == PLUGIN_API_VERSION
    assert protocol["api_version"] == PLUGIN_API_VERSION
    assert protocol["protocol_version"] == PLUGIN_PROTOCOL_VERSION
    assert protocol["limits"]["max_header_bytes"] == limits.max_header_bytes
    assert protocol["limits"]["max_message_bytes"] == limits.max_message_bytes
    assert (
        protocol["limits"]["max_remote_contributions"]
        == MAX_REMOTE_CONTRIBUTIONS
    )

    contracts = {item.kind.value: item for item in CONTRIBUTION_CONTRACTS}
    assert set(protocol["contributions"]) == set(contracts)
    for name, declared in protocol["contributions"].items():
        assert contracts[name].portability.value == declared["portability"]
        if name in {kind.value for kind in _REMOTE_OPERATIONS}:
            operations = _REMOTE_OPERATIONS[contracts[name].kind]
            assert list(operations.names) == declared["operations"]
            assert list(operations.required) == declared["required"]
        else:
            assert declared["portability"] == "native"
            assert not declared["operations"]


def run_reference(language, executable, script):
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--plugin-id", "org.manuskript.reference." + language,
            "--language", language,
            "--cwd", str(script.parent),
            "--timeout", "3",
            "--", executable, script.name,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("PASS:")


def test_python_reference_passes_without_importing_manuskript():
    script = ROOT / "plugin_api" / "reference" / "python" / "plugin.py"
    assert "import manuskript" not in script.read_text(encoding="utf-8").lower()
    run_reference("python", sys.executable, script)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_node_reference_passes_without_an_sdk():
    script = ROOT / "plugin_api" / "reference" / "node" / "plugin.mjs"
    run_reference("node", shutil.which("node"), script)
