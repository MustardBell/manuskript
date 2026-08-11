"""Language-neutral morphology contracts and disposable surface indexes."""

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Protocol, Tuple

from manuskript.domain.canonical_project import (
    EntityRecord,
    StructuredMetadataField,
)


MORPHOLOGY_METADATA = "morphology"


@dataclass(frozen=True)
class MorphologyComponent:
    """One independently inflected component of a compound entity name."""

    role: str
    lemma: str
    attributes: Tuple[Tuple[str, str], ...] = ()
    overrides: Tuple[Tuple[str, str], ...] = ()

    def attribute(self, name: str, default: str = "") -> str:
        return dict(self.attributes).get(name, default)

    def override(self, form_key: str) -> Optional[str]:
        return dict(self.overrides).get(form_key)


@dataclass(frozen=True)
class MorphologyProfile:
    """Author-owned name morphology stored in generic entity metadata."""

    provider_id: str
    components: Tuple[MorphologyComponent, ...]

    @classmethod
    def from_value(cls, value) -> Optional["MorphologyProfile"]:
        if not isinstance(value, Mapping):
            return None
        provider_id = str(value.get("provider", "")).strip()
        raw_components = value.get("components", ())
        if not provider_id or not isinstance(raw_components, list):
            return None
        components = []
        for raw in raw_components:
            if not isinstance(raw, Mapping):
                return None
            role = str(raw.get("role", "name")).strip() or "name"
            lemma = str(raw.get("lemma", "")).strip()
            if not lemma:
                return None
            attributes = raw.get("attributes", {})
            overrides = raw.get("overrides", {})
            if not isinstance(attributes, Mapping) or not isinstance(
                overrides, Mapping
            ):
                return None
            components.append(MorphologyComponent(
                role=role,
                lemma=lemma,
                attributes=tuple(
                    (str(name), str(item))
                    for name, item in attributes.items()
                ),
                overrides=tuple(
                    (str(name), str(item))
                    for name, item in overrides.items()
                    if str(item).strip()
                ),
            ))
        if not components:
            return None
        return cls(provider_id, tuple(components))

    def to_value(self):
        return {
            "version": 1,
            "provider": self.provider_id,
            "components": [
                {
                    "role": component.role,
                    "lemma": component.lemma,
                    "attributes": dict(component.attributes),
                    "overrides": dict(component.overrides),
                }
                for component in self.components
            ],
        }

    @classmethod
    def from_entity(cls, entity: EntityRecord) -> Optional["MorphologyProfile"]:
        value = next(
            (
                item.value for item in reversed(entity.metadata)
                if item.name == MORPHOLOGY_METADATA
            ),
            None,
        )
        return cls.from_value(value)

    def apply_to(self, metadata) -> Tuple[StructuredMetadataField, ...]:
        retained = tuple(
            item for item in metadata if item.name != MORPHOLOGY_METADATA
        )
        return retained + (
            StructuredMetadataField(MORPHOLOGY_METADATA, self.to_value()),
        )


@dataclass(frozen=True)
class GrammaticalForm:
    """A provider-produced surface form with stable feature identity."""

    key: str
    label: str
    text: str
    features: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MorphologyIssue:
    component: int
    message: str


class MorphologyProvider(Protocol):
    id: str
    label: str
    language: str
    component_roles: Tuple[Tuple[str, str], ...]
    genders: Tuple[Tuple[str, str], ...]

    def generate(
        self, component: MorphologyComponent
    ) -> Tuple[GrammaticalForm, ...]:
        ...

    def analyse(
        self, surface: str, component: MorphologyComponent
    ) -> Tuple[GrammaticalForm, ...]:
        ...

    def validate(
        self, component: MorphologyComponent
    ) -> Tuple[str, ...]:
        ...


class MorphologyProviderRegistry:
    """Explicit extension point for deterministic language providers."""

    def __init__(self, providers: Iterable[MorphologyProvider] = ()):
        self._providers = {}
        for provider in providers:
            self.register(provider)

    @property
    def providers(self) -> Tuple[MorphologyProvider, ...]:
        return tuple(self._providers.values())

    def register(self, provider: MorphologyProvider) -> None:
        raw_identifier = getattr(provider, "id", "")
        identifier = (
            raw_identifier.strip()
            if isinstance(raw_identifier, str) else ""
        )
        if (
            not identifier
            or identifier != raw_identifier
            or identifier in self._providers
        ):
            raise ValueError(
                "Morphology provider IDs must be present and unique."
            )
        missing = tuple(
            name for name in ("generate", "analyse", "validate")
            if not callable(getattr(provider, name, None))
        )
        if missing:
            raise ValueError(
                "Morphology providers must implement: {}.".format(
                    ", ".join(missing)
                )
            )
        for name in ("label", "language", "component_roles", "genders"):
            if not hasattr(provider, name):
                raise ValueError(
                    "Morphology providers require a {} attribute.".format(
                        name
                    )
                )
        self._providers[identifier] = provider

    def get(self, provider_id: str) -> Optional[MorphologyProvider]:
        return self._providers.get(str(provider_id))

    def validate(self, profile: MorphologyProfile) -> Tuple[MorphologyIssue, ...]:
        provider = self.get(profile.provider_id)
        if provider is None:
            return (MorphologyIssue(
                -1,
                "Morphology provider is unavailable: {}".format(
                    profile.provider_id
                ),
            ),)
        issues = []
        for index, component in enumerate(profile.components):
            try:
                messages = tuple(provider.validate(component))
            except Exception as error:
                return (MorphologyIssue(
                    index,
                    "Morphology provider {} failed validation: {}: {}"
                    .format(
                        provider.id, type(error).__name__, error
                    ),
                ),)
            issues.extend(
                MorphologyIssue(index, str(message))
                for message in messages
            )
        return tuple(issues)

    def generate(
        self, profile: MorphologyProfile
    ) -> Tuple[GrammaticalForm, ...]:
        provider = self.get(profile.provider_id)
        if provider is None or self.validate(profile):
            return ()
        try:
            paradigms = [
                tuple(provider.generate(item))
                for item in profile.components
            ]
        except Exception:
            return ()
        if any(
            not isinstance(form, GrammaticalForm)
            for forms in paradigms for form in forms
        ):
            return ()
        keys = []
        labels = {}
        by_component = []
        for forms in paradigms:
            mapping = {form.key: form for form in forms}
            by_component.append(mapping)
            for form in forms:
                if form.key not in labels:
                    keys.append(form.key)
                    labels[form.key] = form.label
        result = []
        for key in keys:
            words = []
            features = ()
            for component, forms in zip(profile.components, by_component):
                form = forms.get(key) or forms.get("nominative")
                if form is None:
                    words.append(component.lemma)
                    continue
                words.append(component.override(key) or form.text)
                if not features:
                    features = form.features
            result.append(GrammaticalForm(
                key,
                labels[key],
                " ".join(word for word in words if word),
                features,
            ))
        return tuple(result)


@dataclass(frozen=True)
class EntitySurfaceRealization:
    entity_id: str
    text: str
    source: str
    form_key: str = ""


class MorphologyIndex:
    """Disposable reverse index from written surfaces to entity identity."""

    def __init__(self, providers: MorphologyProviderRegistry):
        self.providers = providers
        self._by_surface = {}
        self._by_entity = {}

    def rebuild(self, entities: Iterable[EntityRecord]) -> None:
        by_surface = {}
        by_entity = {}
        for entity in entities:
            realizations = [
                EntitySurfaceRealization(entity.id, entity.title, "title")
            ]
            realizations.extend(
                EntitySurfaceRealization(entity.id, alias, "alias")
                for alias in entity.aliases
            )
            profile = MorphologyProfile.from_entity(entity)
            if profile is not None:
                realizations.extend(
                    EntitySurfaceRealization(
                        entity.id, form.text, "generated", form.key
                    )
                    for form in self.providers.generate(profile)
                )
            unique = []
            seen = set()
            for realization in realizations:
                key = self.normalize(realization.text)
                if not key or key in seen:
                    continue
                seen.add(key)
                unique.append(realization)
                by_surface.setdefault(key, []).append(realization)
            by_entity[entity.id] = tuple(unique)
        self._by_surface = {
            key: tuple(values) for key, values in by_surface.items()
        }
        self._by_entity = by_entity

    def lookup(self, surface: str) -> Tuple[EntitySurfaceRealization, ...]:
        return self._by_surface.get(self.normalize(surface), ())

    def forms_for(self, entity_id: str) -> Tuple[EntitySurfaceRealization, ...]:
        return self._by_entity.get(entity_id, ())

    @staticmethod
    def normalize(value: str) -> str:
        return " ".join(str(value).split()).casefold()
