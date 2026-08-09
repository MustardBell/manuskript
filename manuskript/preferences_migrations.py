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
PREFERENCES_VERSION = 2

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

#: The fixed keys one window's layout used to occupy, and where each
#: belongs under the per-window shape. Spelled out rather than imported:
#: a migration has to keep working after the new store is renamed.
LEGACY_WINDOW_KEYS = {
    "geometry": "workspace/windows/main/geometry",
    "windowState": "workspace/windows/main/windowState",
    "splitterRedacH":
        "workspace/windows/main/splitters/splitterRedacH",
    "splitterRedacV":
        "workspace/windows/main/splitters/splitterRedacV",
    "metadataState":
        "workspace/windows/main/panelState/core.metadata",
    "revisionsState":
        "workspace/windows/main/panelState/core.metadata.revisions",
}

#: Dock visibility was one map under a single key.
LEGACY_DOCKS_KEY = "docks"

#: The panel titles the toolbar saved visibility against, and the panel
#: ids they became. Matching on button text is what the new shape stops
#: doing, so the last read of those titles happens here.
LEGACY_PANEL_TITLES = {
    "Book summary": "core.book-summary",
    "Project tree": "core.project-tree",
    "Metadata": "core.metadata",
    "Story line": "core.storyline",
}


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


def _v1_to_v2(settings):
    """Window layout moves under the window it belongs to.

    One window's layout used to occupy eight fixed keys, which a second
    window would have written straight over. Everything found there is
    filed under the primary window, so a layout arranged over years
    survives the move.
    """
    for legacy, moved in LEGACY_WINDOW_KEYS.items():
        if settings.contains(legacy):
            settings.setValue(moved, settings.value(legacy))
            settings.remove(legacy)

    if settings.contains(LEGACY_DOCKS_KEY):
        docks = _decode(settings.value(LEGACY_DOCKS_KEY))
        for name, visible in docks.items():
            settings.setValue(
                "workspace/windows/main/docks/{}".format(name),
                bool(visible),
            )
        settings.remove(LEGACY_DOCKS_KEY)

    _migrate_panel_visibility(settings)
    settings.setValue("workspace/version", 1)
    return settings


def _migrate_panel_visibility(settings):
    """Toolbar entries become panel ids.

    Visibility was stored as (group, button text, shown) triples and
    matched back by text, so renaming or translating a panel lost it.
    Titles are read one last time here and never again.
    """
    if not settings.contains("toolbar"):
        return
    raw = settings.value("toolbar")
    settings.remove("toolbar")
    for entry in raw if isinstance(raw, (list, tuple)) else ():
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            continue
        _group, title, shown = entry
        panel_id = LEGACY_PANEL_TITLES.get(
            str(title).replace("&", "")
        )
        if panel_id is None:
            # A panel this Manuskript no longer has. Dropping it is
            # right: nothing can show it, and keeping the row would
            # only preserve a name.
            continue
        settings.setValue(
            "workspace/windows/main/panels/{}".format(panel_id),
            _as_bool(shown),
        )


def _as_bool(value):
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)


#: Ordered (from_version, callable) steps. Each upgrades in place.
MIGRATIONS = (
    (0, _v0_to_v1),
    (1, _v1_to_v2),
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
