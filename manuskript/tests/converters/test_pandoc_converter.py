import importlib
from unittest.mock import MagicMock, patch

import pytest

from manuskript.converters import HTML2PlainText
from manuskript.converters.pandocConverter import pandocConverter
from manuskript.services.external_process import ExternalProcessResult

pandoc_module = importlib.import_module(
    "manuskript.converters.pandocConverter"
)
busy_cursor_module = importlib.import_module(
    "manuskript.ui.busy_cursor"
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
    runner = MagicMock()
    runner.run.return_value = ExternalProcessResult(
        arguments=("pandoc",),
        stdout=b"",
        stderr=b"conversion failed",
        return_code=0,
    )
    report_error = MagicMock()

    with patch.object(
        pandocConverter, "isValid", return_value=2
    ), patch.object(
        busy_cursor_module, "qApp"
    ) as application:
        result = pandocConverter.convert(
            "source",
            on_error=report_error,
            process_runner=runner,
        )

    assert result is None
    report_error.assert_called_once_with("conversion failed")
    application.restoreOverrideCursor.assert_called_once_with()


def test_conversion_restores_cursor_when_process_start_fails():
    runner = MagicMock()
    runner.run.side_effect = OSError("pandoc failed")
    with patch.object(
        pandocConverter, "isValid", return_value=2
    ), patch.object(
        busy_cursor_module, "qApp"
    ) as application:
        with pytest.raises(OSError, match="pandoc failed"):
            pandocConverter.convert(
                "source",
                process_runner=runner,
            )

    application.restoreOverrideCursor.assert_called_once_with()


def test_plain_text_fallback_accepts_html_bytes():
    with patch.object(pandocConverter, "isValid", return_value=0):
        assert HTML2PlainText(b"<p>Hello <b>world</b></p>") == "Hello world"
