import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.converters import HTML2PlainText
from manuskript.converters.pandocConverter import pandocConverter

pandoc_module = importlib.import_module(
    "manuskript.converters.pandocConverter"
)


def test_custom_path_is_valid_and_used_when_pandoc_is_not_on_path():
    with patch.object(pandocConverter, "path", return_value=None), patch.object(
        pandocConverter,
        "customPath",
        return_value="/opt/pandoc",
    ), patch.object(pandoc_module.os.path, "exists", return_value=True):
        assert pandocConverter.isValid() == 1
        assert pandocConverter.runCmd() == "/opt/pandoc"


def test_conversion_reports_stderr_without_owning_a_message_box():
    process = MagicMock()
    process.communicate.return_value = (b"", b"conversion failed")
    report_error = MagicMock()

    with patch.object(pandocConverter, "isValid", return_value=2), patch.object(
        pandoc_module.subprocess,
        "Popen",
        return_value=process,
    ), patch.object(pandoc_module, "qApp") as application:
        result = pandocConverter.convert(
            "source",
            on_error=report_error,
        )

    assert result is None
    report_error.assert_called_once_with("conversion failed")
    application.restoreOverrideCursor.assert_called_once_with()


def test_conversion_restores_cursor_when_process_start_fails():
    with patch.object(pandocConverter, "isValid", return_value=2), patch.object(
        pandoc_module.subprocess,
        "Popen",
        side_effect=OSError("pandoc failed"),
    ), patch.object(pandoc_module, "qApp") as application:
        with pytest.raises(OSError, match="pandoc failed"):
            pandocConverter.convert("source")

    application.restoreOverrideCursor.assert_called_once_with()


def test_plain_text_fallback_accepts_html_bytes():
    with patch.object(pandocConverter, "isValid", return_value=0):
        assert HTML2PlainText(b"<p>Hello <b>world</b></p>") == "Hello world"
