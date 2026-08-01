from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectSaveResult:
    """Outcome of persisting every file that represents a project."""

    failed_files: tuple[str, ...] = ()

    @property
    def succeeded(self):
        return not self.failed_files

    def __bool__(self):
        return self.succeeded


@dataclass(frozen=True)
class ProjectLoadResult:
    """Outcome of hydrating a project from its persisted files."""

    missing_files: tuple[str, ...] = ()
    unreadable_files: tuple[str, ...] = ()
    fatal_errors: tuple[str, ...] = ()

    @property
    def issues(self):
        return (
            self.fatal_errors
            + self.missing_files
            + self.unreadable_files
        )

    @property
    def succeeded(self):
        return not self.fatal_errors

    def __bool__(self):
        return self.succeeded
