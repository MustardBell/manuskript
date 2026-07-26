import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalProcessResult:
    arguments: tuple[str, ...]
    stdout: bytes
    stderr: bytes
    return_code: int


class ExternalProcessRunner:
    """Run a command with piped input and return an immutable result."""

    def __init__(self, popen=None):
        self._popen = popen or subprocess.Popen

    def run(self, arguments, *, stdin=b""):
        arguments = tuple(arguments)
        process = self._popen(
            list(arguments),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(stdin)
        return ExternalProcessResult(
            arguments=arguments,
            stdout=stdout,
            stderr=stderr,
            return_code=process.returncode,
        )
