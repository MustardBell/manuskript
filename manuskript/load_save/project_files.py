import os
import shutil
import stat
import zipfile
from dataclasses import dataclass

from manuskript.domain.persistence import ProjectSaveResult

import logging

LOGGER = logging.getLogger(__name__)
ZIP_COMPRESSION = (
    zipfile.ZIP_DEFLATED
    if getattr(zipfile, "zlib", None) is not None
    else zipfile.ZIP_STORED
)


@dataclass(frozen=True)
class ProjectFileReadResult:
    files: dict
    unreadable_files: tuple[str, ...] = ()


class Version1ProjectFiles:
    """Read and write the physical files used by format version 1."""

    def __init__(self):
        # Permissions of files we have seen, so a file that is deleted and
        # later written again comes back as it was. Without this an undone
        # deletion restores the text but resets the mode, which shows up as
        # noise in a project kept under version control.
        self._modes = {}

    def read(self, project_file, *, zipped):
        if zipped:
            return self._read_zip(project_file)
        return self._read_directory(project_file)

    def write(
        self,
        project_file,
        *,
        zipped,
        files,
        moves,
        cache,
    ):
        if zipped:
            return self._write_zip(project_file, files)
        return self._write_directory(
            project_file,
            files=files,
            moves=moves,
            cache=cache,
        )

    def _read_zip(self, project_file):
        files = {}
        unreadable = []
        with zipfile.ZipFile(project_file) as archive:
            for member in archive.namelist():
                if member.endswith("/"):
                    continue
                path = os.path.normpath(member)
                try:
                    content = archive.read(member)
                    if not self._is_binary(path):
                        content = content.decode("utf-8")
                    files[path] = content
                except (OSError, UnicodeError, zipfile.BadZipFile) as error:
                    LOGGER.error(
                        "Cannot read %s from %s: %s",
                        member,
                        project_file,
                        error,
                    )
                    unreadable.append(path)
        return ProjectFileReadResult(
            files=files,
            unreadable_files=tuple(unreadable),
        )

    def _read_directory(self, project_file):
        root = self._project_directory(project_file)
        files = {}
        unreadable = []

        for directory, directories, filenames in os.walk(root):
            directories[:] = [
                name for name in directories
                if not name.startswith(".")
            ]
            relative_directory = os.path.relpath(directory, root)
            if relative_directory == os.curdir:
                relative_directory = ""

            for name in filenames:
                if name.startswith("."):
                    continue
                relative_path = os.path.normpath(
                    os.path.join(relative_directory, name)
                )
                filename = os.path.join(directory, name)
                self._remember_mode(relative_path, filename)
                try:
                    if self._is_binary(relative_path):
                        with open(filename, "rb") as file_object:
                            content = file_object.read()
                    else:
                        with open(
                            filename,
                            "rt",
                            encoding="utf8",
                        ) as file_object:
                            content = file_object.read()
                    files[relative_path] = content
                except (OSError, UnicodeError) as error:
                    LOGGER.error(
                        "Cannot read %s: %s",
                        filename,
                        error,
                    )
                    unreadable.append(filename)

        return ProjectFileReadResult(
            files=files,
            unreadable_files=tuple(unreadable),
        )

    def _write_zip(self, project_file, files):
        try:
            files = [
                (self._validated_relative_path(path), content)
                for path, content in files
            ]
        except ValueError as error:
            LOGGER.error("Cannot save zip project: %s", error)
            return ProjectSaveResult(
                failed_files=(str(error),)
            )

        try:
            with zipfile.ZipFile(project_file, mode="w") as archive:
                for filename, content in files:
                    archive.writestr(
                        filename,
                        content,
                        compress_type=ZIP_COMPRESSION,
                    )
        except (OSError, zipfile.BadZipFile) as error:
            LOGGER.error(
                "Cannot save zip project %s: %s",
                project_file,
                error,
            )
            return ProjectSaveResult(failed_files=(project_file,))
        return ProjectSaveResult()

    def _write_directory(
        self,
        project_file,
        *,
        files,
        moves,
        cache,
    ):
        failures = []
        root = self._project_directory(project_file)
        project_parent = os.path.dirname(project_file) or os.curdir

        if (
            os.path.exists(project_file)
            and not os.access(project_file, os.W_OK)
        ) or (
            not os.path.exists(project_file)
            and not os.access(project_parent, os.W_OK)
        ):
            LOGGER.error(
                "You don't have write access to save %s.",
                project_file,
            )
            return ProjectSaveResult(failed_files=(project_file,))

        if not cache and os.path.exists(root):
            try:
                shutil.rmtree(root)
            except OSError as error:
                LOGGER.error("Cannot replace %s: %s", root, error)
                return ProjectSaveResult(failed_files=(root,))

        self._move_files(root, moves, cache, failures)
        self._write_files(root, files, cache, failures)
        self._remove_stale_files(root, files, cache, failures)
        self._remove_empty_outline_directories(root)
        self._write_project_marker(project_file, failures)

        return ProjectSaveResult(
            failed_files=tuple(dict.fromkeys(failures))
        )

    def _move_files(self, root, moves, cache, failures):
        for old, new in moves:
            try:
                old_path = self._path_within(root, old)
                new_path = self._path_within(root, new)
                os.makedirs(
                    os.path.dirname(new_path),
                    exist_ok=True,
                )
                os.replace(old_path, new_path)
                LOGGER.debug("* Renaming/moving %s to %s", old, new)
            except FileNotFoundError:
                # A parent directory may already have been renamed.
                pass
            except (OSError, ValueError) as error:
                LOGGER.error(
                    "Cannot rename %s to %s in %s: %s",
                    old,
                    new,
                    root,
                    error,
                )
                failures.append(new)
                continue

            moved_cache = {
                path.replace(old, new): content
                for path, content in cache.items()
            }
            cache.clear()
            cache.update(moved_cache)

    def _write_files(self, root, files, cache, failures):
        for path, content in files:
            if path in cache and cache[path] == content:
                continue

            try:
                filename = self._path_within(root, path)
                os.makedirs(
                    os.path.dirname(filename),
                    exist_ok=True,
                )
                mode = self._mode_to_keep(path, filename)
                if isinstance(content, bytes):
                    with open(filename, "wb") as file_object:
                        file_object.write(content)
                else:
                    with open(
                        filename,
                        "wt",
                        encoding="utf8",
                        newline="\n",
                    ) as file_object:
                        file_object.write(content)
                self._apply_mode(filename, mode)
            except (OSError, ValueError) as error:
                LOGGER.error(
                    "Cannot write %s in %s: %s",
                    path,
                    root,
                    error,
                )
                failures.append(path)
                continue

            cache[path] = content

    def _remember_mode(self, path, filename):
        """Note a file's permissions so a later rewrite can restore them."""
        try:
            self._modes[path] = stat.S_IMODE(os.stat(filename).st_mode)
        except OSError:
            pass

    def _mode_to_keep(self, path, filename):
        """The mode this path should end up with, if we know of one.

        Prefer what is on disk right now; fall back to what the file had
        before it was removed, which is the delete-then-undo case.
        """
        try:
            return stat.S_IMODE(os.stat(filename).st_mode)
        except OSError:
            return self._modes.get(path)

    def _apply_mode(self, filename, mode):
        if mode is None:
            return
        try:
            if stat.S_IMODE(os.stat(filename).st_mode) != mode:
                os.chmod(filename, mode)
        except OSError as error:
            LOGGER.debug(
                "Cannot restore permissions on %s: %s", filename, error
            )

    def _remove_stale_files(self, root, files, cache, failures):
        current_paths = {path for path, _content in files}
        for path in [
            cached_path
            for cached_path in cache
            if cached_path not in current_paths
        ]:
            try:
                filename = self._path_within(root, path)
                self._remember_mode(path, filename)
                if os.path.isdir(filename):
                    shutil.rmtree(filename)
                else:
                    os.remove(filename)
            except FileNotFoundError:
                pass
            except (OSError, ValueError) as error:
                LOGGER.error(
                    "Cannot remove %s from %s: %s",
                    path,
                    root,
                    error,
                )
                failures.append(path)
                continue
            cache.pop(path, None)

    def _remove_empty_outline_directories(self, root):
        outline_root = os.path.join(root, "outline")
        for directory, directories, _files in os.walk(
            outline_root,
            topdown=False,
        ):
            for name in directories:
                path = os.path.join(directory, name)
                try:
                    os.rmdir(path)
                except OSError:
                    # Non-empty and concurrently removed directories are fine.
                    pass

    def _write_project_marker(self, project_file, failures):
        try:
            with open(
                project_file,
                "wt",
                encoding="utf8",
                newline="\n",
            ) as file_object:
                file_object.write("1")
        except OSError as error:
            LOGGER.error(
                "Cannot write project marker %s: %s",
                project_file,
                error,
            )
            failures.append(project_file)

    @staticmethod
    def _project_directory(project_file):
        directory = os.path.dirname(project_file)
        folder = os.path.splitext(
            os.path.basename(project_file)
        )[0]
        return os.path.join(directory, folder)

    @staticmethod
    def _is_binary(path):
        return os.path.splitext(path)[1].lower() in {
            ".xml",
            ".opml",
        }

    @staticmethod
    def _validated_relative_path(path):
        normalized = os.path.normpath(path)
        if (
            os.path.isabs(path)
            or normalized == os.pardir
            or normalized.startswith(os.pardir + os.sep)
        ):
            raise ValueError(
                "Project path escapes its storage root: {}".format(path)
            )
        return normalized

    @classmethod
    def _path_within(cls, root, path):
        normalized = cls._validated_relative_path(path)
        root = os.path.abspath(root)
        candidate = os.path.abspath(os.path.join(root, normalized))
        try:
            within_root = os.path.commonpath(
                (root, candidate)
            ) == root
        except ValueError:
            within_root = False
        if not within_root:
            raise ValueError(
                "Project path escapes its storage root: {}".format(path)
            )
        return candidate
