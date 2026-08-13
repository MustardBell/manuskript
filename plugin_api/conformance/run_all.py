#!/usr/bin/env python3
"""Compile when needed and run every available API-1 reference."""

import argparse
import shutil
import subprocess
import sys
import tempfile

from pathlib import Path

from run import ConformanceFailure, run_profile


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "reference"


def compile_reference(command, timeout=60):
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise ConformanceFailure(
            "compiler failed:\n{}".format(result.stderr.strip())
        )


def available_profiles(build):
    profiles = {
        "python": (
            [sys.executable, "plugin.py"], REFERENCES / "python"
        ),
    }
    node = shutil.which("node")
    if node:
        profiles["node"] = ([node, "plugin.mjs"], REFERENCES / "node")
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler:
        suffix = ".exe" if sys.platform == "win32" else ""
        executable = build / ("c-plugin" + suffix)
        compile_reference([
            compiler, "-std=c11", "-O2",
            str(REFERENCES / "c" / "plugin.c"), "-o", str(executable),
        ])
        profiles["c"] = ([str(executable)], build)
    rustc = shutil.which("rustc")
    if rustc:
        suffix = ".exe" if sys.platform == "win32" else ""
        executable = build / ("rust-plugin" + suffix)
        compile_reference([
            rustc, "--edition=2021", "-O",
            str(REFERENCES / "rust" / "plugin.rs"),
            "-o", str(executable),
        ])
        profiles["rust"] = ([str(executable)], build)
    escript = shutil.which("escript")
    if escript:
        profiles["erlang"] = (
            [escript, "plugin.escript"], REFERENCES / "erlang"
        )
    return profiles


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require",
        default="",
        help="comma-separated languages that must be available",
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)
    required = {item.strip() for item in args.require.split(",") if item.strip()}
    with tempfile.TemporaryDirectory(prefix="manuskript-api-1-") as temporary:
        profiles = available_profiles(Path(temporary))
        missing = sorted(required - set(profiles))
        if missing:
            print(
                "FAIL: required language tools are unavailable: {}"
                .format(", ".join(missing)),
                file=sys.stderr,
            )
            return 1
        for language in ("python", "node", "c", "rust", "erlang"):
            if language not in profiles:
                print("SKIP: {} toolchain is unavailable".format(language))
                continue
            command, cwd = profiles[language]
            try:
                run_profile(
                    "org.manuskript.reference." + language,
                    language,
                    command,
                    cwd,
                    args.timeout,
                )
            except ConformanceFailure as error:
                print("FAIL {}: {}".format(language, error), file=sys.stderr)
                return 1
            print("PASS: {}".format(language))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
