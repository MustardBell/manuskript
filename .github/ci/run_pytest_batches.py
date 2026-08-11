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
WORKSPACE_FIXTURES = frozenset((
    "MW",
    "MWEmptyProject",
    "MWNoProject",
    "MWSampleProject",
    "test_application",
))


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
    workspace_files = tuple(path for path in files if uses_workspace_fixture(path))
    shared_files = tuple(path for path in files if path not in workspace_files)
    # A MainWindow is session-scoped inside pytest. Give each file requesting
    # that fixture its own process; pure domain and lightweight widget files
    # remain efficiently balanced into shared processes.
    batches = (
        *balanced_batches(shared_files, arguments.batches),
        *((path,) for path in workspace_files),
    )
    planned = tuple(path for batch in batches for path in batch)
    if len(planned) != len(files) or set(planned) != set(files):
        raise RuntimeError("test batching lost or duplicated a file")

    print(
        "Planned {} test files in {} batches ({}s hard limit each).".format(
            len(files), len(batches), arguments.timeout_seconds
        ),
        flush=True,
    )
    for number, batch in enumerate(batches, 1):
        weight = sum(path.stat().st_size for path in batch)
        print(
            "Batch {}/{}: {} files, {} source bytes".format(
                number, len(batches), len(batch), weight
            ),
            flush=True,
        )
        if arguments.plan:
            continue
        return_code = run_batch(batch, arguments.timeout_seconds)
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
