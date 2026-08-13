"""Safe discovery and compilation of declarative morphology packs."""

import logging
import os
import sys

from pathlib import Path

from lxml import etree as ET

from manuskript.domain.morphology import (
    CHOICE,
    TEXT,
    MorphologyAttributeSpec,
    MorphologyFormSpec,
    MorphologyLexeme,
    MorphologyRule,
    MorphologySchema,
    MorphologySchemaRegistry,
    MorphologyTransform,
)


LOGGER = logging.getLogger(__name__)
PACK_SUFFIX = ".morphology.xml"


class MorphologyPackError(ValueError):
    """A pack is unsafe, malformed, or incomplete."""


def built_in_pack_path() -> Path:
    return Path(__file__).resolve().parent / "packs"


def user_pack_path() -> Path:
    """Match Manuskript's application-data location without importing Qt."""

    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return root / "manuskript" / "manuskript" / "morphology"


def parse_morphology_pack(source, *, source_name="<memory>") -> MorphologySchema:
    """Compile one XML pack to the neutral domain representation.

    Entities and network access are disabled.  The resulting object contains
    data and bounded core operations only; loading a pack never imports or
    executes language-specific code.
    """

    parser = ET.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=True,
    )
    try:
        raw = source.encode("utf-8") if isinstance(source, str) else source
        root = ET.fromstring(raw, parser=parser)
    except (ET.XMLSyntaxError, TypeError, ValueError) as error:
        raise MorphologyPackError(
            "Cannot parse morphology pack {}: {}".format(source_name, error)
        ) from error
    if root.tag != "morphology-pack":
        raise MorphologyPackError(
            "Morphology pack {} must have a morphology-pack root.".format(
                source_name
            )
        )

    identifier = _required(root, "id", source_name)
    label = _required(root, "label", source_name)
    language = _required(root, "language", source_name)
    version = _required(root, "version", source_name)
    components = root.find("components")
    forms_element = root.find("forms")
    if components is None or forms_element is None:
        raise MorphologyPackError(
            "Morphology pack {} requires components and forms.".format(
                source_name
            )
        )
    default_role = _required(components, "default-role", source_name)
    roles = tuple(
        (
            _required(item, "id", source_name),
            _required(item, "label", source_name),
        )
        for item in components.findall("role")
    )
    attributes = tuple(
        _attribute(item, source_name)
        for item in components.findall("attribute")
    )
    forms = tuple(_form(item, source_name) for item in forms_element.findall("form"))

    paradigms = root.find("paradigms")
    rules = () if paradigms is None else tuple(
        _rule(item, source_name) for item in paradigms.findall("paradigm")
    )
    lexicon_element = root.find("lexicon")
    lexicon = () if lexicon_element is None else tuple(
        _lexeme(item, source_name) for item in lexicon_element.findall("lexeme")
    )
    try:
        schema = MorphologySchema(
            identifier,
            label,
            language,
            version,
            default_role,
            roles,
            attributes,
            forms,
            rules,
            lexicon,
        )
        # Reuse registry validation so files and programmatically constructed
        # schemas have exactly one contract.
        MorphologySchemaRegistry((schema,))
        return schema
    except (TypeError, ValueError) as error:
        raise MorphologyPackError(
            "Invalid morphology pack {}: {}".format(source_name, error)
        ) from error


def load_morphology_schemas(paths, *, strict=False) -> MorphologySchemaRegistry:
    registry = MorphologySchemaRegistry()
    for root in tuple(Path(path) for path in paths):
        if not root.exists():
            continue
        files = (root,) if root.is_file() else sorted(root.glob("*" + PACK_SUFFIX))
        for filename in files:
            try:
                schema = parse_morphology_pack(
                    filename.read_bytes(), source_name=str(filename)
                )
                registry.register(schema)
            except (OSError, MorphologyPackError, TypeError, ValueError) as error:
                if strict:
                    raise
                LOGGER.warning("Ignoring morphology pack %s: %s", filename, error)
    return registry


def first_party_morphology_schemas() -> MorphologySchemaRegistry:
    return load_morphology_schemas((built_in_pack_path(),), strict=True)


def installed_morphology_schemas() -> MorphologySchemaRegistry:
    """Load shipped and dropped-in packs through the same parser."""

    builtins = first_party_morphology_schemas()
    user = load_morphology_schemas((user_pack_path(),), strict=False)
    for schema in user.schemas:
        try:
            builtins.register(schema)
        except ValueError as error:
            LOGGER.warning("Ignoring user morphology schema %s: %s", schema.id, error)
    return builtins


def _required(element, name, source_name):
    value = str(element.attrib.get(name, "")).strip()
    if not value:
        raise MorphologyPackError(
            "Morphology pack {} has a {} without {}.".format(
                source_name, element.tag, name
            )
        )
    return value


def _attribute(element, source_name):
    kind = str(element.attrib.get("kind", CHOICE)).strip()
    if kind not in (TEXT, CHOICE):
        raise MorphologyPackError(
            "Morphology attribute kind must be text or choice in {}.".format(
                source_name
            )
        )
    choices = tuple(
        (
            _required(item, "value", source_name),
            _required(item, "label", source_name),
        )
        for item in element.findall("choice")
    )
    if kind == CHOICE and not choices:
        raise MorphologyPackError(
            "Choice morphology attributes require choices in {}.".format(source_name)
        )
    return MorphologyAttributeSpec(
        _required(element, "id", source_name),
        _required(element, "label", source_name),
        kind,
        str(element.attrib.get("default", "")),
        choices,
        str(element.attrib.get("required", "false")).casefold() == "true",
    )


def _form(element, source_name):
    return MorphologyFormSpec(
        _required(element, "id", source_name),
        _required(element, "label", source_name),
        tuple(
            (
                _required(item, "name", source_name),
                _required(item, "value", source_name),
            )
            for item in element.findall("feature")
        ),
    )


def _rule(element, source_name):
    attributes = []
    for condition in element.findall("when"):
        key = _required(condition, "attribute", source_name)
        values = tuple(
            value for value in str(condition.attrib.get("values", "")).split()
            if value
        )
        if not values:
            raise MorphologyPackError(
                "Morphology rule conditions require values in {}.".format(source_name)
            )
        attributes.append((key, values))
    return MorphologyRule(
        _required(element, "id", source_name),
        tuple(
            value for value in str(element.attrib.get("roles", "")).split()
            if value
        ),
        tuple(attributes),
        str(element.attrib.get("pattern", "")),
        tuple(
            MorphologyTransform(
                _required(item, "form", source_name),
                int(item.attrib.get("strip", "0")),
                str(item.attrib.get("append", "")),
            )
            for item in element.findall("surface")
        ),
    )


def _lexeme(element, source_name):
    return MorphologyLexeme(
        _required(element, "lemma", source_name),
        str(element.attrib.get("role", "")),
        tuple(
            (
                _required(item, "attribute", source_name),
                _required(item, "value", source_name),
            )
            for item in element.findall("when")
        ),
        tuple(
            (
                _required(item, "form", source_name),
                _required(item, "text", source_name),
            )
            for item in element.findall("surface")
        ),
    )
