import zipfile
from dataclasses import dataclass


class ProjectFormatError(ValueError):
    pass


@dataclass(frozen=True)
class DetectedProjectFormat:
    version: int
    zipped: bool


class ProjectFormatDetector:
    """Detect a project format without mutating project state."""

    ZIP_MARKERS = ("VERSION", "MANUSKRIPT")

    def detect(self, project_file):
        try:
            with zipfile.ZipFile(project_file) as archive:
                return self._detect_zip(project_file, archive)
        except zipfile.BadZipFile:
            return self._detect_plain_text(project_file)
        except OSError as error:
            raise ProjectFormatError(
                "Cannot read project {}: {}".format(
                    project_file,
                    error,
                )
            ) from error

    def _detect_zip(self, project_file, archive):
        names = set(archive.namelist())
        for marker in self.ZIP_MARKERS:
            if marker in names:
                value = archive.read(marker)
                return DetectedProjectFormat(
                    version=self._parse_version(
                        value,
                        project_file,
                        marker,
                    ),
                    zipped=True,
                )
        return DetectedProjectFormat(version=0, zipped=True)

    def _detect_plain_text(self, project_file):
        try:
            with open(
                project_file,
                "rt",
                encoding="utf-8",
            ) as project:
                value = project.read()
        except (OSError, UnicodeError) as error:
            raise ProjectFormatError(
                "Cannot read project {}: {}".format(
                    project_file,
                    error,
                )
            ) from error
        return DetectedProjectFormat(
            version=self._parse_version(
                value,
                project_file,
                "project",
            ),
            zipped=False,
        )

    @staticmethod
    def _parse_version(value, project_file, marker):
        if isinstance(value, bytes):
            try:
                value = value.decode("ascii")
            except UnicodeDecodeError as error:
                raise ProjectFormatError(
                    "Invalid {} marker in {}".format(
                        marker,
                        project_file,
                    )
                ) from error
        if not value.isdigit():
            raise ProjectFormatError(
                "Invalid {} marker in {}".format(
                    marker,
                    project_file,
                )
            )
        return int(value)


class ProjectFormatRegistry:
    """Resolve an explicit serializer strategy for a format version."""

    def __init__(self, handlers, current_version):
        self._handlers = dict(handlers)
        self.current_version = current_version
        if current_version not in self._handlers:
            raise ValueError(
                "Current project format has no registered handler."
            )

    def resolve(self, version=None):
        selected = (
            self.current_version
            if version is None
            else version
        )
        try:
            return selected, self._handlers[selected]
        except KeyError as error:
            raise ProjectFormatError(
                "Unsupported project format version: {}".format(
                    selected
                )
            ) from error
