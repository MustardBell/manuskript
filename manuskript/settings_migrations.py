"""Versioned upgrades for the settings stored inside a project.

Settings live in ``settings.txt`` inside every project archive, so a key that
changes shape has to be converted on load or old projects silently lose the
value. This mirrors the project-format handling in
``manuskript.load_save.format_detection``: an absent version marker means
version 0, and each step from there is explicit.

Migrations are the only place legacy settings vocabulary is allowed to appear.
Everything downstream of :func:`upgrade` sees current-shape data.
"""

import logging


LOGGER = logging.getLogger(__name__)

#: Bump when adding a migration, and append the step to MIGRATIONS.
SETTINGS_VERSION = 1

VERSION_KEY = "settingsVersion"


def _v0_to_v1(data):
    """Cork card styles become plugin-style identifiers.

    Until 2026 the cork delegate chose between two hard-coded renderers using
    ``corkStyle`` set to ``"old"`` or ``"new"``. Card styles are now
    contributions addressed by ID, so the two built-ins take the IDs they
    would have had all along.
    """
    legacy = data.pop("corkStyle", None)
    data["indexCardStyle"] = {
        "old": "manuskript.card.ruled",
        "new": "manuskript.card.plain",
    }.get(legacy, "manuskript.card.plain")
    return data


#: Ordered (from_version, callable) steps. Each returns the upgraded mapping.
MIGRATIONS = (
    (0, _v0_to_v1),
)


def upgrade(data):
    """Bring a settings mapping up to :data:`SETTINGS_VERSION`.

    A mapping with no version marker is treated as version 0, which is what
    every project written before versioning existed looks like.
    """
    version = _detected_version(data)
    if version > SETTINGS_VERSION:
        # Written by a newer Manuskript. Refusing would make the project
        # unopenable, so load what we understand and leave the rest alone.
        LOGGER.warning(
            "Project settings are version %s but this Manuskript "
            "understands %s. Loading anyway; unknown values are ignored.",
            version,
            SETTINGS_VERSION,
        )
        return data

    for from_version, migrate in MIGRATIONS:
        if version <= from_version:
            data = migrate(data)
            version = from_version + 1

    data[VERSION_KEY] = SETTINGS_VERSION
    return data


def _detected_version(data):
    try:
        return int(data.get(VERSION_KEY, 0))
    except (TypeError, ValueError):
        LOGGER.warning(
            "Ignoring unreadable settings version %r; treating as 0.",
            data.get(VERSION_KEY),
        )
        return 0
