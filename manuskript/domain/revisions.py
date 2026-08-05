from dataclasses import dataclass
from enum import Enum


class RevisionBackendKind(str, Enum):
    """Persisted identifiers for the available revision implementations."""

    INTERNAL = "internal"
    GIT = "git"

    @classmethod
    def from_value(cls, value):
        try:
            return cls(value)
        except (TypeError, ValueError):
            # Git is the supported backend; internal snapshots are legacy.
            return cls.GIT


@dataclass(frozen=True)
class RevisionConfiguration:
    """Backend-independent view of project revision settings."""

    enabled: bool
    backend: RevisionBackendKind
    auto_commit: bool = False
    tagged_only: bool = False

    @classmethod
    def from_mapping(cls, settings):
        settings = settings or {}
        git_settings = settings.get("git") or {}
        return cls(
            enabled=bool(settings.get("keep", False)),
            backend=RevisionBackendKind.from_value(
                settings.get(
                    "backend",
                    RevisionBackendKind.GIT.value,
                )
            ),
            auto_commit=bool(
                git_settings.get("autoCommit", False)
            ),
            tagged_only=bool(
                git_settings.get("taggedOnly", False)
            ),
        )

    @property
    def uses_internal_snapshots(self):
        return (
            self.enabled
            and self.backend is RevisionBackendKind.INTERNAL
        )

    @property
    def uses_git(self):
        return (
            self.enabled
            and self.backend is RevisionBackendKind.GIT
        )
