from unittest.mock import MagicMock

from manuskript.services.external_tools import (
    ExternalTool,
    ExternalToolAvailability,
    ExternalToolPaths,
)


def test_tool_paths_use_canonical_key_and_read_legacy_key():
    settings = MagicMock()
    settings.contains.side_effect = (
        lambda key: key == "Exporters/Pandoc_customPath"
    )
    settings.value.return_value = "/opt/pandoc"
    paths = ExternalToolPaths(settings)

    assert paths.get("pandoc") == "/opt/pandoc"

    paths.set("Pandoc", "/new/pandoc")
    settings.setValue.assert_called_once_with(
        "Exporters/pandoc_customPath",
        "/new/pandoc",
    )


def test_external_tool_prefers_system_command():
    paths = MagicMock()
    paths.get.return_value = "/custom/pandoc"
    tool = ExternalTool(
        "pandoc",
        "pandoc",
        paths=paths,
        which=lambda _command: "/usr/bin/pandoc",
        exists=lambda _path: True,
    )

    assert tool.availability is ExternalToolAvailability.SYSTEM
    assert tool.executable == "pandoc"


def test_external_tool_uses_custom_command_when_system_is_missing():
    paths = MagicMock()
    paths.get.return_value = "/custom/pandoc"
    run = MagicMock(return_value=b"pandoc 3")
    tool = ExternalTool(
        "pandoc",
        "pandoc",
        paths=paths,
        which=lambda _command: None,
        exists=lambda _path: True,
        check_output=run,
    )

    assert tool.availability is ExternalToolAvailability.CUSTOM
    assert tool.run_text(["--version"]) == "pandoc 3"
    run.assert_called_once_with(
        ["/custom/pandoc", "--version"]
    )


def test_setting_custom_path_delegates_to_path_store():
    paths = MagicMock()
    tool = ExternalTool(
        "pandoc",
        "pandoc",
        paths=paths,
    )

    tool.custom_path = "/opt/pandoc"

    paths.set.assert_called_once_with("pandoc", "/opt/pandoc")
