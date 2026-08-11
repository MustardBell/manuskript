"""Project-codec contracts and a version-indexed registry."""

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence, Tuple

from manuskript.domain.canonical_project import (
    CanonicalProject,
    ProjectContent,
    ProjectIssue,
)


@dataclass(frozen=True)
class EncodedProject:
    format_version: int
    files: Tuple[Tuple[str, ProjectContent], ...]


class ProjectCodec(Protocol):
    format_version: int

    def decode(
        self,
        files: Mapping[str, ProjectContent],
        *,
        zipped: bool = False,
    ) -> CanonicalProject:
        ...

    def encode(self, project: CanonicalProject) -> EncodedProject:
        ...

    def validate(self, project: CanonicalProject) -> Tuple[ProjectIssue, ...]:
        ...


class ProjectCodecRegistry:
    """Resolve codecs without importing UI serializers."""

    def __init__(self, codecs: Sequence[ProjectCodec]):
        self._codecs = {codec.format_version: codec for codec in codecs}

    def resolve(self, version: int) -> ProjectCodec:
        try:
            return self._codecs[version]
        except KeyError as error:
            raise ValueError(
                "Unsupported project format version: {}".format(version)
            ) from error

    @property
    def versions(self) -> Tuple[int, ...]:
        return tuple(sorted(self._codecs))
