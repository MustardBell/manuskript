"""Persistence capability negotiation for projects and plugins."""

from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Tuple


class PersistenceLevel(Enum):
    NATIVE = "native"
    COMPATIBLE_ENCODING = "compatible-encoding"
    OVERLAY = "overlay"
    DERIVED = "derived"
    READ_ONLY = "read-only"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FeatureSupport:
    feature: str
    persistence_level: PersistenceLevel
    readable: bool
    writable: bool
    old_client_readable: bool
    old_client_editable: bool
    old_client_save_safe: bool
    reason: str = ""

    @property
    def supported(self) -> bool:
        return self.persistence_level is not PersistenceLevel.UNSUPPORTED


def unsupported(feature: str, reason: str = "") -> FeatureSupport:
    return FeatureSupport(
        feature=feature,
        persistence_level=PersistenceLevel.UNSUPPORTED,
        readable=False,
        writable=False,
        old_client_readable=False,
        old_client_editable=False,
        old_client_save_safe=False,
        reason=reason,
    )


class ProjectPersistenceStrategy:
    """Answer feature questions without leaking a format number to callers."""

    name = "abstract"

    def __init__(self, support: Optional[Mapping[str, FeatureSupport]] = None):
        self._support = dict(support or {})

    def support(self, feature: str) -> FeatureSupport:
        return self._support.get(
            feature,
            unsupported(feature, "The persistence strategy has no encoding."),
        )

    def supports(self, feature: str, write: bool = False) -> bool:
        result = self.support(feature)
        return result.writable if write else result.readable

    def catalogue(self) -> Tuple[FeatureSupport, ...]:
        return tuple(self._support[name] for name in sorted(self._support))


class PersistenceDecorator(ProjectPersistenceStrategy):
    """Extend a strategy without shadowing data owned by the wrapped format."""

    namespace = ""

    def __init__(
        self,
        wrapped: ProjectPersistenceStrategy,
        support: Iterable[FeatureSupport],
    ):
        self.wrapped = wrapped
        additions = {item.feature: item for item in support}
        overlap = set(additions).intersection(
            item.feature for item in wrapped.catalogue()
        )
        if overlap:
            raise ValueError(
                "Persistence decorators cannot shadow owned features: {}".format(
                    ", ".join(sorted(overlap))
                )
            )
        if self.namespace:
            invalid = [
                name for name in additions
                if not name.startswith(self.namespace + ".")
            ]
            if invalid:
                raise ValueError(
                    "Decorator features must live below {!r}: {}".format(
                        self.namespace,
                        ", ".join(sorted(invalid)),
                    )
                )
        super().__init__(additions)

    @property
    def name(self) -> str:
        return self.wrapped.name + "+" + self.namespace

    def support(self, feature: str) -> FeatureSupport:
        if feature in self._support:
            return self._support[feature]
        return self.wrapped.support(feature)

    def catalogue(self) -> Tuple[FeatureSupport, ...]:
        combined = {
            item.feature: item for item in self.wrapped.catalogue()
        }
        combined.update(self._support)
        return tuple(combined[name] for name in sorted(combined))


def _support(
    feature: str,
    level: PersistenceLevel,
    *,
    writable: bool = True,
    old_readable: bool = True,
    old_editable: bool = True,
    old_save_safe: bool = True,
    reason: str = "",
) -> FeatureSupport:
    return FeatureSupport(
        feature=feature,
        persistence_level=level,
        readable=True,
        writable=writable,
        old_client_readable=old_readable,
        old_client_editable=old_editable,
        old_client_save_safe=old_save_safe,
        reason=reason,
    )


class V1PersistenceStrategy(ProjectPersistenceStrategy):
    name = "manuskript-v1"

    def __init__(self):
        super().__init__({
            item.feature: item for item in (
                _support("project.metadata", PersistenceLevel.NATIVE),
                _support("outline.read", PersistenceLevel.NATIVE),
                _support("outline.write", PersistenceLevel.NATIVE),
                _support("manuscript.markdown", PersistenceLevel.NATIVE),
                _support("legacy.characters", PersistenceLevel.NATIVE),
                _support("legacy.world", PersistenceLevel.NATIVE),
                _support("legacy.plots", PersistenceLevel.NATIVE),
                _support("revisions.snapshots", PersistenceLevel.NATIVE),
                _support(
                    "plugins.project-files",
                    PersistenceLevel.OVERLAY,
                    old_readable=False,
                    old_editable=False,
                    old_save_safe=False,
                    reason=(
                        "Old clients rebuild archives and remove unrecognized "
                        "folder files while saving."
                    ),
                ),
            )
        })


class V2PersistenceStrategy(ProjectPersistenceStrategy):
    name = "manuskript-v2"

    def __init__(self):
        native = (
            "project.metadata",
            "outline.read",
            "outline.write",
            "manuscript.markdown",
            "entities.read",
            "entities.write",
            "references.read",
            "references.write",
            "morphology.entities",
            "assertions.read",
            "assertions.write",
            "timeline.read",
            "timeline.write",
            "plugins.project-files",
        )
        super().__init__({
            name: _support(
                name,
                PersistenceLevel.NATIVE,
                old_readable=False,
                old_editable=False,
                old_save_safe=False,
                reason="Project Format 2 is not understood by old clients.",
            )
            for name in native
        })


class WikilinkPersistenceDecorator(PersistenceDecorator):
    namespace = "references"

    def __init__(self, wrapped: ProjectPersistenceStrategy):
        super().__init__(wrapped, (
            _support(
                "references.read",
                PersistenceLevel.COMPATIBLE_ENCODING,
                reason="Wikilinks remain ordinary manuscript text to v1 clients.",
            ),
            _support(
                "references.write",
                PersistenceLevel.COMPATIBLE_ENCODING,
                reason="Wikilinks remain ordinary manuscript text to v1 clients.",
            ),
        ))


class MorphologyPersistenceDecorator(PersistenceDecorator):
    namespace = "morphology"

    def __init__(self, wrapped: ProjectPersistenceStrategy):
        super().__init__(wrapped, (
            _support(
                "morphology.entities",
                PersistenceLevel.COMPATIBLE_ENCODING,
                old_readable=True,
                old_editable=True,
                old_save_safe=True,
                reason="Stored in safely preserved character custom fields.",
            ),
        ))


class StoryOverlayPersistenceDecorator(PersistenceDecorator):
    namespace = "story"

    def __init__(self, wrapped: ProjectPersistenceStrategy):
        super().__init__(wrapped, (
            _support(
                "story.assertions",
                PersistenceLevel.OVERLAY,
                old_readable=False,
                old_editable=False,
                old_save_safe=False,
                reason="v1 has no native assertion representation.",
            ),
            _support(
                "story.timeline",
                PersistenceLevel.OVERLAY,
                old_readable=False,
                old_editable=False,
                old_save_safe=False,
                reason="v1 has no native temporal assertion representation.",
            ),
        ))


def compatibility_strategy(version: int) -> ProjectPersistenceStrategy:
    if version == 1:
        return StoryOverlayPersistenceDecorator(
            MorphologyPersistenceDecorator(
                WikilinkPersistenceDecorator(V1PersistenceStrategy())
            )
        )
    if version == 2:
        return V2PersistenceStrategy()
    return ProjectPersistenceStrategy()
