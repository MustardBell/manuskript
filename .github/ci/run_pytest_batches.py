"""Run the host test suite in bounded, deterministic Python processes.

Qt owns native objects outside Python's garbage collector.  Keeping every GUI
test in one interpreter makes a late native teardown capable of aborting the
remaining suite without a traceback.  CI still runs every test file; it merely
gives a bounded group of files one QApplication and one process lifetime.
"""

import argparse
import ast
import os
from pathlib import Path
import signal
import subprocess
import sys
from typing import Iterable, List, Sequence, Tuple


DEFAULT_BATCHES = 8
DEFAULT_TIMEOUT_SECONDS = 90
SLOW_TEST_TIMEOUT_SECONDS = 600
SLOW_TEST_FILES = frozenset(("test_conformance_package.py",))
WORKSPACE_FIXTURES = frozenset((
    "MW",
    "MWEmptyProject",
    "MWNoProject",
    "MWSampleProject",
    "test_application",
))
NATIVE_UI_IMPORTS = (
    "PyQt5",
    "PySide",
    "manuskript.ui",
)


def test_files(root: Path) -> Tuple[Path, ...]:
    return tuple(sorted(root.rglob("test_*.py")))


def uses_workspace_fixture(path: Path) -> bool:
    """Whether a file owns the session-scoped Manuskript window."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        if any(argument.arg in WORKSPACE_FIXTURES for argument in arguments):
            return True
    return False


def uses_native_ui(path: Path) -> bool:
    """Whether a file directly enters Qt or Manuskript's UI layer.

    Qt owns native state beyond Python's object graph. Even files that do not
    request the complete workspace can leave a widget, timer, or queued event
    behind for the next file in the process. Keep such files individually
    bounded; pure domain files can still share efficient batches.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return any(
        module.startswith(prefix)
        for module in modules
        for prefix in NATIVE_UI_IMPORTS
    )


def requires_isolated_process(path: Path) -> bool:
    return (
        uses_workspace_fixture(path)
        or uses_native_ui(path)
        or path.name in SLOW_TEST_FILES
    )


def batch_timeout(files: Sequence[Path], default: int) -> int:
    """Return the hard ceiling for one process.

    Cross-language conformance compiles the no-SDK C and Rust references on
    the platform under test. A cold Windows toolchain legitimately needs more
    than the normal UI/domain ceiling, so that file gets an isolated process
    and an explicit larger limit rather than making every test less bounded.

    The ceiling must exceed the file's own inner timeouts, not merely one of
    them: two compilers at up to four minutes each, plus five protocol
    exchanges. A ceiling below them turns a specific "rustc was slow" into an
    unhelpful "the batch timed out".
    """

    if any(path.name in SLOW_TEST_FILES for path in files):
        return max(default, SLOW_TEST_TIMEOUT_SECONDS)
    return default


def balanced_batches(
    files: Iterable[Path], count: int
) -> Tuple[Tuple[Path, ...], ...]:
    """Distribute files by source size with stable, complete assignment."""

    if count < 1:
        raise ValueError("batch count must be positive")
    buckets: List[List[Path]] = [[] for _ in range(count)]
    weights = [0] * count
    ranked = sorted(
        files,
        key=lambda path: (-path.stat().st_size, path.as_posix()),
    )
    for path in ranked:
        target = min(range(count), key=lambda index: (weights[index], index))
        buckets[target].append(path)
        weights[target] += path.stat().st_size
    return tuple(tuple(sorted(bucket)) for bucket in buckets if bucket)


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ("taskkill", "/F", "/T", "/PID", str(process.pid)),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    os.killpg(process.pid, signal.SIGKILL)


def run_batch(files: Sequence[Path], timeout_seconds: int) -> int:
    command = (
        sys.executable,
        "-m",
        "pytest",
        "-v",
        "--maxfail=1",
        *(path.as_posix() for path in files),
    )
    process = subprocess.Popen(
        command,
        start_new_session=os.name != "nt",
        creationflags=(
            subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        ),
    )
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        process.wait()
        return 124


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("manuskript/tests"))
    parser.add_argument("--batches", type=int, default=DEFAULT_BATCHES)
    parser.add_argument(
        "--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS
    )
    parser.add_argument("--plan", action="store_true")
    arguments = parser.parse_args(argv or None)

    files = test_files(arguments.root)
    isolated_files = tuple(path for path in files if requires_isolated_process(path))
    shared_files = tuple(path for path in files if path not in isolated_files)
    # A MainWindow is session-scoped inside pytest, and lighter Qt files can
    # still leave native state outside Python's collector. Give every file
    # that directly enters the UI boundary its own process; pure domain files
    # remain efficiently balanced into shared processes.
    batches = (
        *balanced_batches(shared_files, arguments.batches),
        *((path,) for path in isolated_files),
    )
    planned = tuple(path for batch in batches for path in batch)
    if len(planned) != len(files) or set(planned) != set(files):
        raise RuntimeError("test batching lost or duplicated a file")

    print(
        "Planned {} test files in {} batches ({}s default hard limit).".format(
            len(files), len(batches), arguments.timeout_seconds
        ),
        flush=True,
    )
    for number, batch in enumerate(batches, 1):
        weight = sum(path.stat().st_size for path in batch)
        timeout_seconds = batch_timeout(batch, arguments.timeout_seconds)
        print(
            "Batch {}/{}: {} files, {} source bytes, {}s hard limit".format(
                number, len(batches), len(batch), weight, timeout_seconds
            ),
            flush=True,
        )
        if arguments.plan:
            continue
        return_code = run_batch(batch, timeout_seconds)
        if return_code:
            print(
                "Batch {} failed with exit code {}.".format(
                    number, return_code
                ),
                flush=True,
            )
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
