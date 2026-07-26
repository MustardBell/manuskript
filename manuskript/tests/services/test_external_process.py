from unittest.mock import MagicMock

from manuskript.services.external_process import ExternalProcessRunner


def test_external_process_runner_returns_immutable_process_data():
    process = MagicMock()
    process.communicate.return_value = (b"output", b"warning")
    process.returncode = 0
    popen = MagicMock(return_value=process)
    runner = ExternalProcessRunner(popen=popen)

    result = runner.run(
        ["pandoc", "--version"],
        stdin=b"source",
    )

    assert result.arguments == ("pandoc", "--version")
    assert result.stdout == b"output"
    assert result.stderr == b"warning"
    assert result.return_code == 0
    process.communicate.assert_called_once_with(b"source")
