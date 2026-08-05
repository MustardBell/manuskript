"""Versioned upgrades for preferences stored outside any project.

Application preferences live in ``QSettings``, not in the ``settings.txt``
inside a project archive, so they need their own version marker and their own
ordered steps. :mod:`manuskript.settings_migrations` handles the other half
and the two must not be confused: a project written by another author carries
its settings, but the routing choices a person made are theirs and follow
them between projects.

The shape is deliberately the same as its project-side counterpart. An absent
marker means version 0, which is what every installation predating versioning
looks like, and each step from there is explicit.

Migrations are the only place legacy preference vocabulary is allowed to
appear. Everything downstream of :func:`upgrade` sees current-shape data.
"""

import json
import logging

from manuskript.media_types import (
    BBCODE,
    DOCX,
    EPUB,
    HTML,
    LATEX,
    MARKDOWN,
    ODT,
    OPML,
    PDF,
    PLAIN,
    RST,
)


LOGGER = logging.getLogger(__name__)

#: Bump when adding a migration, and append the step to MIGRATIONS.
PREFERENCES_VERSION = 1

VERSION_KEY = "preferencesVersion"

#: Where page renderer choices are stored. Spelled out rather than imported:
#: the halves live on PluginOptionStore and PageTypeService, and a migration
#: has to keep working after either of them is renamed.
ROUTE_KEY_PREFIX = "plugins/options/manuskript.page-renderers."

#: The short names exporters used before they named formats by media type.
LEGACY_MEDIA_TYPES = {
    "plain": PLAIN,
    "markdown": MARKDOWN,
    "html": HTML,
    "bbcode": BBCODE,
    "latex": LATEX,
    "rst": RST,
    "opml": OPML,
    "epub": EPUB,
    "odt": ODT,
    "docx": DOCX,
    "pdf": PDF,
}

#: The separator legacy route identifiers joined on.
LEGACY_SEPARATOR = ":"


def _v0_to_v1(settings):
    """Page renderer routes become pairs of media types.

    Routing choices were keyed by short format names -- ``bbcode:bbcode``,
    and before that by the representation alone -- which cannot survive
    formats being named by media type. Both older shapes are rewritten, so
    a choice made years ago still selects the renderer it selected then.
    """
    for key in list(settings.allKeys()):
        if not key.startswith(ROUTE_KEY_PREFIX):
            continue
        stored = _decode(settings.value(key))
        if not stored:
            continue
        migrated = {
            _migrate_route(route): renderer_id
            for route, renderer_id in stored.items()
        }
        if migrated != stored:
            settings.setValue(
                key,
                json.dumps(migrated, ensure_ascii=False, sort_keys=True),
            )
    return settings


def _route_syntax():
    """How route identifiers are spelled, imported only when needed.

    ``manuskript.exporter.page_routes`` looks harmless, but importing it
    executes the exporter package, which reaches Qt exporter settings
    widgets and from there ``manuskript.ui.style``. That module snapshots
    ``qApp.palette()`` at import time, so pulling it in from a module
    ``main`` imports would freeze the palette before the application style
    is chosen, and every derived colour in the interface would be wrong.
    """
    from manuskript.exporter.page_routes import (
        ROUTE_SEPARATOR,
        page_renderer_route_id,
    )

    return ROUTE_SEPARATOR, page_renderer_route_id


def _migrate_route(route):
    """One stored route identifier, in whatever shape it was written."""
    separator, page_renderer_route_id = _route_syntax()
    route = str(route)
    if separator in route:
        # Already a pair of media types.
        return route
    if LEGACY_SEPARATOR in route:
        output, _, representation = route.rpartition(LEGACY_SEPARATOR)
        return page_renderer_route_id(
            _media_type(output),
            _media_type(representation),
        )
    # Older still: the representation alone, which named the route where a
    # format is both what pages are composed in and what comes out.
    media_type = _media_type(route)
    return page_renderer_route_id(media_type, media_type)


def _media_type(name):
    """A legacy short name as a media type, or itself when unrecognised.

    An unknown name came from something that named its own formats, and
    guessing at it would be worse than leaving it inert and visible.
    """
    return LEGACY_MEDIA_TYPES.get(name, name)


def _decode(value):
    if value is None:
        return {}
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


#: Ordered (from_version, callable) steps. Each upgrades in place.
MIGRATIONS = (
    (0, _v0_to_v1),
)


def upgrade(settings):
    """Bring stored preferences up to :data:`PREFERENCES_VERSION`."""
    version = _detected_version(settings)
    if version > PREFERENCES_VERSION:
        # Written by a newer Manuskript. Refusing would leave the person
        # without their preferences, so keep what we understand.
        LOGGER.warning(
            "Preferences are version %s but this Manuskript understands "
            "%s. Loading anyway; unknown values are left alone.",
            version,
            PREFERENCES_VERSION,
        )
        return settings

    for from_version, migrate in MIGRATIONS:
        if version <= from_version:
            settings = migrate(settings)
            version = from_version + 1

    settings.setValue(VERSION_KEY, PREFERENCES_VERSION)
    settings.sync()
    return settings


def _detected_version(settings):
    raw = settings.value(VERSION_KEY, 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        LOGGER.warning(
            "Ignoring unreadable preferences version %r; treating as 0.",
            raw,
        )
        return 0
