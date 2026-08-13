"""Run every maintained submodule's tests in isolated bounded processes."""

import configparser
import sys

from pathlib import Path

from run_pytest_batches import run_batch, test_files


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TIMEOUT_SECONDS = 90


def maintained_plugin_roots():
    configuration = configparser.ConfigParser()
    configuration.read(ROOT / ".gitmodules", encoding="utf-8")
    roots = []
    for section in configuration.sections():
        path = configuration.get(section, "path", fallback="").strip()
        if path:
            roots.append(ROOT / path)
    return tuple(roots)


def main():
    files = tuple(
        test_file
        for plugin_root in maintained_plugin_roots()
        for test_file in test_files(plugin_root / "tests")
    )
    if not files:
        print("No maintained plugin tests were found.", file=sys.stderr)
        return 1
    print(
        "Running {} maintained plugin test files in separate processes."
        .format(len(files)),
        flush=True,
    )
    for number, test_file in enumerate(files, 1):
        print(
            "Plugin test {}/{}: {}".format(
                number,
                len(files),
                test_file.relative_to(ROOT),
            ),
            flush=True,
        )
        return_code = run_batch((test_file,), DEFAULT_TIMEOUT_SECONDS)
        if return_code:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
