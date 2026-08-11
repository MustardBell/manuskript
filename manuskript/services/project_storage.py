import logging

from manuskript import loadSave
from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.load_save.legacy_archive import Version0ProjectArchive
from manuskript.load_save.format_detection import (
    ProjectFormatDetector,
)
from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.project_files import ProjectFileReadResult
from manuskript.load_save.version_1_codec import (
    REQUIRED_FILES,
    Version1ProjectCodec,
)
from manuskript.load_save.version_0_codec import Version0ProjectCodec
from manuskript.services.legacy_project_adapter import (
    LegacyApplicationModelAdapter,
)
from manuskript.domain.project_features import compatibility_strategy


LOGGER = logging.getLogger(__name__)


class ProjectStorage:
    """Persistence boundary and exception shield for the project lifecycle."""

    def __init__(
        self,
        file_cache=None,
        file_access=None,
        legacy_file_access=None,
        format_detector=None,
        version_1_codec=None,
        version_0_codec=None,
        application_model_adapter=None,
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
        self._format_detector = format_detector or ProjectFormatDetector()
        self._version_1_codec = version_1_codec or Version1ProjectCodec()
        self._version_0_codec = version_0_codec or Version0ProjectCodec()
        self._application_model_adapter = (
            application_model_adapter or LegacyApplicationModelAdapter()
        )
        self._canonical_project = None

    @property
    def canonical_project(self):
        return self._canonical_project

    @property
    def persistence_strategy(self):
        if self._canonical_project is None:
            return compatibility_strategy(-1)
        return compatibility_strategy(
            self._canonical_project.format_version
        )

    def load(self, context):
        try:
            detected = self._format_detector.detect(context.project_file)
            if detected.version == 1:
                return self._load_version_1(
                    context,
                    zipped=detected.zipped,
                    file_access=self._file_access,
                )
            if detected.version == 0:
                self._canonical_project = self._version_0_codec.decode(
                    self._legacy_file_access.read(context.project_file),
                    zipped=True,
                )
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
            selected_version = 1 if version is None else version
            if selected_version == 1:
                return self._save_version_1(context)
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
            return self._load_version_1(
                context,
                zipped=snapshot.zipped,
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
        self._canonical_project = None

    def _load_version_1(self, context, *, zipped, file_access):
        read_result = file_access.read(
            context.project_file,
            zipped=bool(zipped),
        )
        project = self._version_1_codec.decode(
            read_result.files,
            zipped=bool(zipped),
        )
        self._application_model_adapter.hydrate(project, context)
        self._canonical_project = project
        if not zipped:
            self._file_cache.clear()
            self._file_cache.update(read_result.files)
        missing = tuple(
            path for path in REQUIRED_FILES
            if path not in read_result.files
        )
        diagnostics = tuple(
            "{}: {}".format(issue.source.path, issue.message)
            for issue in project.issues
            if issue.source.path not in missing
        )
        return ProjectLoadResult(
            missing_files=missing,
            unreadable_files=read_result.unreadable_files,
            diagnostics=diagnostics,
        )

    def _save_version_1(self, context):
        before = self._canonical_project or self._version_1_codec.decode(
            {}, zipped=bool(context.settings.saveToZip)
        )
        project = self._application_model_adapter.capture(context, before)
        encoded = self._version_1_codec.encode(project)
        result = self._file_access.write(
            context.project_file,
            zipped=project.zipped,
            files=encoded.files,
            moves=self._application_model_adapter.moves(before, project),
            cache=self._file_cache,
        )
        if result.succeeded:
            self._canonical_project = self._version_1_codec.decode(
                dict(encoded.files), zipped=project.zipped
            )
        return result

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
