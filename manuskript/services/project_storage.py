import logging

from manuskript import loadSave
from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.load_save.legacy_archive import Version0ProjectArchive
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.project_files import ProjectFileReadResult
from manuskript.load_save import version_1


LOGGER = logging.getLogger(__name__)


class ProjectStorage:
    """Persistence boundary and exception shield for the project lifecycle."""

    def __init__(
        self,
        file_cache=None,
        file_access=None,
        legacy_file_access=None,
    ):
        self._file_cache = (
            file_cache if file_cache is not None else {}
        )
        self._file_access = (
            file_access
            if file_access is not None
            else Version1ProjectFiles()
        )
        self._legacy_file_access = (
            legacy_file_access
            if legacy_file_access is not None
            else Version0ProjectArchive()
        )

    def load(self, context):
        try:
            return loadSave.loadProject(
                context,
                cache=self._file_cache,
                file_access=self._file_access,
                legacy_file_access=self._legacy_file_access,
            )
        except Exception as error:
            message = self._failure_message("load", context, error)
            LOGGER.exception(message)
            return ProjectLoadResult(fatal_errors=(message,))

    def save(self, context, version=None):
        try:
            return loadSave.saveProject(
                context,
                version=version,
                cache=self._file_cache,
                file_access=self._file_access,
                legacy_file_access=self._legacy_file_access,
            )
        except Exception as error:
            LOGGER.exception(
                self._failure_message("save", context, error)
            )
            return ProjectSaveResult(
                failed_files=(context.project_file,)
            )

    def load_snapshot(self, context, snapshot):
        """Hydrate models from immutable in-memory project files."""
        try:
            return version_1.loadProject(
                context,
                zip=snapshot.zipped,
                cache={},
                file_access=InMemoryProjectFiles(snapshot.files),
            )
        except Exception as error:
            message = self._failure_message(
                "load revision snapshot",
                context,
                error,
            )
            LOGGER.exception(message)
            return ProjectLoadResult(fatal_errors=(message,))

    def clear_cache(self):
        self._file_cache.clear()

    @staticmethod
    def _failure_message(operation, context, error):
        return "Cannot {} project {}: {}: {}".format(
            operation,
            context.project_file,
            type(error).__name__,
            error,
        )


class InMemoryProjectFiles:
    """Version-1 file reader backed by an already materialized snapshot."""

    def __init__(self, files):
        self._files = dict(files)

    def read(self, _project_file, *, zipped):
        return ProjectFileReadResult(files=dict(self._files))
