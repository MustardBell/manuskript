import os

import pytest

from manuskript.plugins.runtimes import (
    ProcessRuntime,
    PythonRuntime,
    RuntimeKind,
)


def test_python_runtime_keeps_language_details_out_of_the_manifest_loader():
    runtime = PythonRuntime("package.plugin", "register")

    assert runtime.kind is RuntimeKind.PYTHON
    assert runtime.module == "package.plugin"
    assert runtime.callable == "register"


@pytest.mark.parametrize("module", ["bad-name", "../plugin", "plugin:one"])
def test_python_runtime_rejects_ambiguous_modules(module):
    with pytest.raises(ValueError, match="module is invalid"):
        PythonRuntime(module, "register")


def test_process_runtime_resolves_plugin_executable_without_a_shell(tmp_path):
    executable = tmp_path / "bin" / "plugin"
    executable.parent.mkdir()
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    runtime = ProcessRuntime(1, {
        "linux": ["bin/plugin", "--literal", "$(not-a-shell)"],
    })

    availability = runtime.availability(tmp_path, "linux")

    assert availability.available
    assert availability.command == (
        str(executable.resolve()),
        "--literal",
        "$(not-a-shell)",
    )


def test_process_runtime_reports_missing_external_language_runtime(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("PATH", "")
    runtime = ProcessRuntime(1, {
        "linux": ["definitely-missing-node", "plugin.mjs"],
    })

    availability = runtime.availability(tmp_path, "linux")

    assert not availability.available
    assert "Required runtime executable" in availability.error
    assert "definitely-missing-node" in availability.error


def test_process_runtime_reports_an_unsupported_host_platform(tmp_path):
    runtime = ProcessRuntime(1, {"windows": ["plugin.exe"]})

    availability = runtime.availability(tmp_path, "linux")

    assert not availability.available
    assert "does not provide a linux process command" in availability.error


@pytest.mark.parametrize(
    "executable",
    ["../escape", "/absolute/plugin", "C:\\absolute\\plugin.exe"],
)
def test_process_runtime_cannot_escape_the_plugin_directory(executable):
    with pytest.raises(ValueError, match="inside|relative"):
        ProcessRuntime(1, {"linux": [executable]})


def test_process_runtime_requires_argument_arrays_not_shell_strings():
    with pytest.raises(ValueError, match="argument array"):
        ProcessRuntime(1, {"linux": "node plugin.mjs"})


def test_process_runtime_declaration_is_immutable():
    runtime = ProcessRuntime(1, {"linux": ["node", "plugin.mjs"]})

    with pytest.raises(TypeError):
        runtime.commands["linux"] = ("other",)

    assert runtime.kind is RuntimeKind.PROCESS
    assert os.fspath("plugin.mjs") in runtime.commands["linux"]
