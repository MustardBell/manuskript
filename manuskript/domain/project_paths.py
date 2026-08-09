"""Portable names for files stored inside a Manuskript project.

Project file names are serialized data, not host filesystem paths.  Keep
their representation stable across Linux, macOS, and Windows, and translate
to native separators only at the disk boundary.
"""

import ntpath
import os
import posixpath


def normalize_project_path(path):
    """Return a safe, project-relative path using ``/`` separators."""
    raw_path = os.fspath(path).replace("\\", "/")
    drive, _tail = ntpath.splitdrive(raw_path)
    normalized = posixpath.normpath(raw_path)
    if (
        not raw_path
        or drive
        or raw_path.startswith("/")
        or normalized in (".", "..")
        or normalized.startswith("../")
    ):
        raise ValueError(
            "Project path escapes its storage root: {}".format(path)
        )
    return normalized


def project_path_on_disk(root, path):
    """Resolve a portable project path beneath a native filesystem root."""
    normalized = normalize_project_path(path)
    root = os.path.abspath(root)
    candidate = os.path.abspath(
        os.path.join(root, *normalized.split("/"))
    )
    try:
        within_root = os.path.commonpath((root, candidate)) == root
    except ValueError:
        within_root = False
    if not within_root:
        raise ValueError(
            "Project path escapes its storage root: {}".format(path)
        )
    return candidate
