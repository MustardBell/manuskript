"""Declarative, language-agnostic morphology and disposable indexes.

Core owns the mechanics in this module.  A morphology pack owns every piece
of linguistic vocabulary: roles, feature axes, paradigms, form names, rules,
and lexical exceptions.  Persisted author overrides remain useful even when
the pack that originally described them is not installed.
"""

import re

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Tuple

from manuskript.domain.canonical_project import (
    EntityRecord,
    StructuredMetadataField,
)


MORPHOLOGY_METADATA = "morphology"
TEXT = "text"
CHOICE = "choice"


def normalize_language_tag(value: str) -> str:
    """Return a stable, well-formed BCP 47 spelling without resolving it.

    Morphology does not need to know whether a tag is registered or what it
    means.  It does need a safe namespace.  Underscores are accepted at the
    input boundary because operating-system locale spellings commonly use
    them; persisted language tags use BCP 47's hyphen separator.
    """

    tag = str(value or "").strip().replace("_", "-")
    parts = tag.split("-")
    if (
        not tag
        or any(not part or len(part) > 8 or not part.isalnum() for part in parts)
        or not parts[0].isalpha()
        or (parts[0].casefold() != "x" and not 2 <= len(parts[0]) <= 8)
    ):
        raise ValueError("A morphology language must be a well-formed BCP 47 tag.")
    return "-".join(part.casefold() for part in parts)


@dataclass(frozen=True)
class MorphologyComponent:
    """One independently realized lexeme in a compound expression."""

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
    """Author-owned morphology independent of any installed pack."""

    language_tag: str
    schema_id: str
    components: Tuple[MorphologyComponent, ...]

    def __post_init__(self):
        object.__setattr__(
            self, "language_tag", normalize_language_tag(self.language_tag)
        )
        object.__setattr__(self, "schema_id", str(self.schema_id or "").strip())
        object.__setattr__(self, "components", tuple(self.components))

    @classmethod
    def from_value(cls, value) -> Optional["MorphologyProfile"]:
        if not isinstance(value, Mapping):
            return None
        # This is the first public morphology representation.  Earlier
        # development-only provider metadata is intentionally not treated as
        # a compatibility contract.
        language_tag = str(value.get("language", "")).strip()
        schema_id = str(value.get("schema", "")).strip()
        raw_components = value.get("components", ())
        if not language_tag or not isinstance(raw_components, list):
            return None
        components = []
        for raw in raw_components:
            if not isinstance(raw, Mapping):
                return None
            role = str(raw.get("role", "")).strip()
            lemma = str(raw.get("lemma", "")).strip()
            attributes = raw.get("attributes", {})
            overrides = raw.get("overrides", {})
            if (
                not lemma
                or not isinstance(attributes, Mapping)
                or not isinstance(overrides, Mapping)
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
        try:
            return cls(language_tag, schema_id, tuple(components))
        except ValueError:
            return None

    def to_value(self):
        return {
            "version": 1,
            "language": self.language_tag,
            "schema": self.schema_id,
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
class MorphologyAttributeSpec:
    """One schema-declared, otherwise opaque component feature."""

    key: str
    label: str
    kind: str = TEXT
    default: str = ""
    choices: Tuple[Tuple[str, str], ...] = ()
    required: bool = False


@dataclass(frozen=True)
class MorphologyFormSpec:
    key: str
    label: str
    features: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MorphologyTransform:
    form_key: str
    strip: int = 0
    append: str = ""

    def apply(self, lemma: str) -> str:
        if self.strip > len(lemma):
            return self.append
        stem = lemma[:-self.strip] if self.strip else lemma
        return stem + self.append


@dataclass(frozen=True)
class MorphologyRule:
    """A schema rule selected by opaque role, features, and text pattern."""

    id: str
    roles: Tuple[str, ...] = ()
    attributes: Tuple[Tuple[str, Tuple[str, ...]], ...] = ()
    pattern: str = ""
    transforms: Tuple[MorphologyTransform, ...] = ()

    def matches(self, component: MorphologyComponent) -> bool:
        if self.roles and component.role not in self.roles:
            return False
        values = dict(component.attributes)
        if any(values.get(key, "") not in accepted for key, accepted in self.attributes):
            return False
        return not self.pattern or re.search(self.pattern, component.lemma) is not None


@dataclass(frozen=True)
class MorphologyLexeme:
    lemma: str
    role: str = ""
    attributes: Tuple[Tuple[str, str], ...] = ()
    forms: Tuple[Tuple[str, str], ...] = ()

    def matches(self, component: MorphologyComponent) -> bool:
        if self.lemma.casefold() != component.lemma.casefold():
            return False
        if self.role and self.role != component.role:
            return False
        values = dict(component.attributes)
        return all(values.get(key, "") == value for key, value in self.attributes)


@dataclass(frozen=True)
class MorphologySchema:
    """Validated declarative morphology pack compiled to core's neutral IR."""

    id: str
    label: str
    language_tag: str
    version: str
    default_role: str
    component_roles: Tuple[Tuple[str, str], ...]
    attributes: Tuple[MorphologyAttributeSpec, ...]
    forms: Tuple[MorphologyFormSpec, ...]
    rules: Tuple[MorphologyRule, ...] = ()
    lexicon: Tuple[MorphologyLexeme, ...] = ()

    def __post_init__(self):
        object.__setattr__(
            self, "language_tag", normalize_language_tag(self.language_tag)
        )

    def defaults(self) -> Tuple[Tuple[str, str], ...]:
        return tuple(
            (field.key, field.default)
            for field in self.attributes if field.default
        )


@dataclass(frozen=True)
class GrammaticalForm:
    """A generated surface form with stable, schema-owned feature identity."""

    key: str
    label: str
    text: str
    features: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class MorphologyIssue:
    component: int
    message: str
    blocking: bool = True


class DeclarativeMorphologyEngine:
    """Apply a compiled pack without knowing any linguistic feature names."""

    def generate(
        self, schema: MorphologySchema, component: MorphologyComponent
    ) -> Tuple[GrammaticalForm, ...]:
        lexical = next(
            (entry for entry in schema.lexicon if entry.matches(component)),
            None,
        )
        lexical_forms = dict(lexical.forms) if lexical is not None else {}
        rule = next(
            (candidate for candidate in schema.rules if candidate.matches(component)),
            None,
        )
        transforms = {
            item.form_key: item for item in (() if rule is None else rule.transforms)
        }
        return tuple(
            GrammaticalForm(
                form.key,
                form.label,
                lexical_forms.get(
                    form.key,
                    transforms[form.key].apply(component.lemma)
                    if form.key in transforms else component.lemma,
                ),
                form.features,
            )
            for form in schema.forms
        )

    def analyse(
        self,
        schema: MorphologySchema,
        surface: str,
        component: MorphologyComponent,
    ) -> Tuple[GrammaticalForm, ...]:
        normalized = self.normalize(surface)
        return tuple(
            form for form in self.generate(schema, component)
            if self.normalize(component.override(form.key) or form.text) == normalized
        )

    @staticmethod
    def normalize(value: str) -> str:
        return " ".join(str(value).split()).casefold()


class MorphologySchemaRegistry:
    """Project-facing catalogue of declarative packs and one neutral engine."""

    def __init__(
        self,
        schemas: Iterable[MorphologySchema] = (),
        engine: Optional[DeclarativeMorphologyEngine] = None,
    ):
        self._schemas = {}
        self.engine = engine or DeclarativeMorphologyEngine()
        for schema in schemas:
            self.register(schema)

    @property
    def schemas(self) -> Tuple[MorphologySchema, ...]:
        return tuple(self._schemas.values())

    def register(self, schema: MorphologySchema) -> None:
        if not isinstance(schema, MorphologySchema):
            raise TypeError("Morphology extensions must be declarative schemas.")
        identifier = schema.id
        if not identifier or identifier != identifier.strip() or identifier in self._schemas:
            raise ValueError("Morphology schema IDs must be present and unique.")
        if not schema.forms:
            raise ValueError("A morphology schema must declare at least one form.")
        role_ids = tuple(item[0] for item in schema.component_roles)
        if len(set(role_ids)) != len(role_ids) or schema.default_role not in role_ids:
            raise ValueError("Morphology roles must be unique and include the default.")
        form_ids = tuple(item.key for item in schema.forms)
        if len(set(form_ids)) != len(form_ids):
            raise ValueError("Morphology form IDs must be unique.")
        field_ids = tuple(item.key for item in schema.attributes)
        if len(set(field_ids)) != len(field_ids):
            raise ValueError("Morphology attribute IDs must be unique.")
        for rule in schema.rules:
            if rule.pattern:
                try:
                    re.compile(rule.pattern)
                except re.error as error:
                    raise ValueError(
                        "Invalid morphology rule pattern {}: {}".format(
                            rule.id, error
                        )
                    ) from error
            unknown = set(item.form_key for item in rule.transforms) - set(form_ids)
            if unknown:
                raise ValueError(
                    "Morphology rule {} uses unknown forms: {}".format(
                        rule.id, ", ".join(sorted(unknown))
                    )
                )
        self._schemas[identifier] = schema

    def get(self, schema_id: str) -> Optional[MorphologySchema]:
        return self._schemas.get(str(schema_id))

    def validate(self, profile: MorphologyProfile) -> Tuple[MorphologyIssue, ...]:
        schema = self.get(profile.schema_id)
        if schema is None:
            return (MorphologyIssue(
                -1,
                "Morphology schema is unavailable: {}".format(
                    profile.schema_id or profile.language_tag
                ),
                blocking=False,
            ),)
        issues = []
        role_ids = dict(schema.component_roles)
        fields = {item.key: item for item in schema.attributes}
        for index, component in enumerate(profile.components):
            if not component.lemma.strip():
                issues.append(MorphologyIssue(index, "A lexeme may not be empty."))
            if component.role not in role_ids:
                issues.append(MorphologyIssue(
                    index,
                    "The schema does not describe role: {}".format(component.role),
                    blocking=False,
                ))
            values = dict(component.attributes)
            for field in fields.values():
                value = values.get(field.key, "")
                if field.required and not value:
                    issues.append(MorphologyIssue(
                        index, "{} is required.".format(field.label)
                    ))
                if field.choices and value and value not in dict(field.choices):
                    issues.append(MorphologyIssue(
                        index,
                        "{} has an unknown value: {}".format(field.label, value),
                        blocking=False,
                    ))
        return tuple(issues)

    def generate_component(
        self, schema_id: str, component: MorphologyComponent
    ) -> Tuple[GrammaticalForm, ...]:
        schema = self.get(schema_id)
        return () if schema is None else self.engine.generate(schema, component)

    def generate(
        self, profile: MorphologyProfile
    ) -> Tuple[GrammaticalForm, ...]:
        schema = self.get(profile.schema_id)
        if schema is None:
            return self._manual_forms(profile)
        if any(issue.blocking for issue in self.validate(profile)):
            return ()
        paradigms = tuple(
            self.engine.generate(schema, component)
            for component in profile.components
        )
        result = []
        for form in schema.forms:
            words = []
            for component, generated in zip(profile.components, paradigms):
                item = next((entry for entry in generated if entry.key == form.key), None)
                words.append(
                    component.override(form.key)
                    or (item.text if item is not None else component.lemma)
                )
            result.append(GrammaticalForm(
                form.key,
                form.label,
                " ".join(word for word in words if word),
                form.features,
            ))
        return tuple(result)

    def analyse(
        self,
        profile: MorphologyProfile,
        surface: str,
    ) -> Tuple[GrammaticalForm, ...]:
        normalized = self.engine.normalize(surface)
        return tuple(
            form for form in self.generate(profile)
            if self.engine.normalize(form.text) == normalized
        )

    @staticmethod
    def _manual_forms(profile: MorphologyProfile) -> Tuple[GrammaticalForm, ...]:
        keys = []
        for component in profile.components:
            for key, _value in component.overrides:
                if key not in keys:
                    keys.append(key)
        return tuple(
            GrammaticalForm(
                key,
                key,
                " ".join(
                    component.override(key) or component.lemma
                    for component in profile.components
                ),
            )
            for key in keys
        )


@dataclass(frozen=True)
class EntitySurfaceRealization:
    entity_id: str
    text: str
    source: str
    form_key: str = ""


class MorphologyIndex:
    """Disposable reverse index from written surfaces to entity identity."""

    def __init__(self, schemas: MorphologySchemaRegistry, enabled=True):
        self.schemas = schemas
        self._enabled = bool(enabled)
        self._by_surface = {}
        self._by_entity = {}

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

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
            profile = (
                MorphologyProfile.from_entity(entity)
                if self._enabled else None
            )
            if profile is not None:
                realizations.extend(
                    EntitySurfaceRealization(
                        entity.id, form.text, "generated", form.key
                    )
                    for form in self.schemas.generate(profile)
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
