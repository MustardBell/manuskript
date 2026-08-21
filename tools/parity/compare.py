"""Run the probe against upstream and against this branch, and diff them.

Upstream is a commit in this repository's own history, checked out into a
worktree. That is the oracle: the expected answer is produced by running
Manuskript as it was, so if upstream turns out to do something surprising,
upstream wins rather than anybody's description of it.

Both runs get their own empty settings directory. A probe that inherited
the developer's settings would compare two arrangements a reader had made
rather than two the code produces.
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile


#: The upstream commit this fork is measured against.
UPSTREAM = "7abdba31abbd97bfdd80e72786fe2191d7f42d4a"

HERE = pathlib.Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]


def _project(root):
    """A deterministic project both versions can open."""

    book = root / "book"
    (book / "outline").mkdir(parents=True, exist_ok=True)
    (root / "book.msk").write_text("1", encoding="utf-8")
    (book / "settings.txt").write_text("{}", encoding="utf-8")
    (book / "outline" / "scene.md").write_text(
        "She left quietly.", encoding="utf-8"
    )
    return root / "book.msk"


def _run(checkout, project, home):
    """One reading, in its own process and its own settings directory."""

    probe = checkout / "tools" / "parity" / "probe.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    if not probe.exists():
        shutil.copy(HERE / "probe.py", probe)
    environment = dict(os.environ)
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
    })
    home.mkdir(parents=True, exist_ok=True)
    finished = subprocess.run(
        [sys.executable, str(probe), str(project)],
        cwd=str(checkout), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
    )
    if finished.returncode:
        raise RuntimeError(
            "probe failed in {}:\n{}".format(
                checkout, finished.stderr.decode("utf-8", "replace")
            )
        )
    return json.loads(finished.stdout.decode("utf-8"))


def differences(upstream, fork, path=""):
    """Every place the two readings disagree, as a flat list."""

    if isinstance(upstream, dict) and isinstance(fork, dict):
        found = []
        for key in sorted(set(upstream) | set(fork)):
            found.extend(differences(
                upstream.get(key), fork.get(key), "{}/{}".format(path, key)
            ))
        return found
    if isinstance(upstream, list) and isinstance(fork, list):
        found = []
        for index in range(max(len(upstream), len(fork))):
            found.extend(differences(
                upstream[index] if index < len(upstream) else None,
                fork[index] if index < len(fork) else None,
                "{}[{}]".format(path, index),
            ))
        return found
    if upstream != fork:
        return [(path, upstream, fork)]
    return []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", default=UPSTREAM)
    parser.add_argument(
        "--ignore", action="append", default=["/opened_by"],
        help="path prefixes that may legitimately differ",
    )
    arguments = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as scratch:
        scratch = pathlib.Path(scratch)
        project = _project(scratch / "project")
        tree = scratch / "upstream"
        subprocess.run(
            ["git", "-C", str(REPOSITORY), "worktree", "add", "--detach",
             str(tree), arguments.upstream],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            upstream = _run(tree, project, scratch / "home-upstream")
            fork = _run(REPOSITORY, project, scratch / "home-fork")
        finally:
            subprocess.run(
                ["git", "-C", str(REPOSITORY), "worktree", "remove",
                 "--force", str(tree)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    found = [
        entry for entry in differences(upstream, fork)
        if not any(entry[0].startswith(prefix) for prefix in arguments.ignore)
    ]
    for where, was, now in found:
        print("{}\n    upstream: {!r}\n    fork:     {!r}".format(
            where, was, now
        ))
    print("\n{} differences".format(len(found)))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
