"""First-party and installed declarative language resources."""

from manuskript.linguistics.morphology_packs import (
    MorphologyPackError,
    built_in_pack_path,
    first_party_morphology_schemas,
    installed_morphology_schemas,
    load_morphology_schemas,
    parse_morphology_pack,
    user_pack_path,
)


__all__ = (
    "MorphologyPackError",
    "built_in_pack_path",
    "first_party_morphology_schemas",
    "installed_morphology_schemas",
    "load_morphology_schemas",
    "parse_morphology_pack",
    "user_pack_path",
)
