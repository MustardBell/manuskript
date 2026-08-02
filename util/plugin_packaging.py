import argparse
import configparser
from pathlib import Path


RUNTIME_NAMES = ("plugin.json", "LICENSE")


def shipped_plugin_directories(plugin_root, gitmodules=".gitmodules"):
    plugin_root = Path(plugin_root).resolve()
    gitmodules = Path(gitmodules)
    if not plugin_root.is_dir() or not gitmodules.is_file():
        return []
    parser = configparser.ConfigParser()
    parser.read(str(gitmodules), encoding="utf-8")
    directories = []
    for section in parser.sections():
        if not section.startswith("submodule ") or not parser.has_option(
            section, "path"
        ):
            continue
        directory = (gitmodules.parent / parser.get(section, "path")).resolve()
        if (
            directory.parent == plugin_root
            and (directory / "plugin.json").is_file()
        ):
            directories.append(directory)
    return sorted(set(directories))


def plugin_data_entries(plugin_root, gitmodules=".gitmodules"):
    """Return PyInstaller data entries for installed plugin repositories.

    Plugins are runtime-loaded from source, so their top-level Python files
    and manifest must remain ordinary files beside a packaged application.
    Tests, repository metadata, caches, and documentation are deliberately
    not part of the executable payload.
    """
    entries = []
    for directory in shipped_plugin_directories(plugin_root, gitmodules):
        destination = directory.relative_to(
            Path(gitmodules).resolve().parent
        ).as_posix()
        files = [
            path
            for path in directory.glob("*.py")
            if path.is_file()
        ]
        files.extend(
            directory / name
            for name in RUNTIME_NAMES
            if (directory / name).is_file()
        )
        entries.extend(
            (path.as_posix(), destination)
            for path in sorted(set(files))
        )
    return entries


def rsync_filter_lines(plugin_root, gitmodules=".gitmodules"):
    plugin_root = Path(plugin_root)
    root_line = "+ /{}/".format(plugin_root.as_posix().rstrip("/"))
    lines = [root_line]
    lines.extend(
        "+ /{}/***".format(
            directory.relative_to(
                Path(gitmodules).resolve().parent
            ).as_posix()
        )
        for directory in shipped_plugin_directories(plugin_root, gitmodules)
    )
    lines.append("- /{}/*/".format(plugin_root.as_posix().rstrip("/")))
    return tuple(lines)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--rsync-filter", metavar="PATH")
    args = parser.parse_args(argv)
    if args.rsync_filter:
        Path(args.rsync_filter).write_text(
            "\n".join(rsync_filter_lines("manuskript/plugins")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
