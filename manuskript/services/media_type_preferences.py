"""What the user chose about media types, kept between sessions.

A fallback answers "nothing produces this format, so what should stand in?"
and that answer is the user's, not a project's: it follows them between
manuscripts the same way their chosen renderers do. So it lives in
``QSettings`` beside those, and :mod:`manuskript.preferences_migrations`
versions it.
"""

import json
import logging

from PyQt5.QtCore import QSettings

from manuskript.media_types import USER, MediaType, MediaTypeError


LOGGER = logging.getLogger(__name__)


class MediaTypePreferences:
    """Load and store the user's media type choices for a registry."""

    FALLBACK_KEY = "media-types/fallbacks"
    OVERRIDE_KEY = "media-types/overrides"
    DECLARATION_KEY = "media-types/declarations"

    def __init__(self, settings=None):
        self._settings = (
            settings if settings is not None else QSettings()
        )

    # ------------------------------------------------------------ loading

    def apply(self, registry):
        """Put stored choices into a registry, skipping ones it refuses.

        Declarations go in first, because a fallback or an override may name
        a format only the user introduced.

        Every entry can be stale. The format a choice named may have gone
        with an uninstalled plugin, and a pair that was fine when saved can
        close a loop once other choices change. Neither should stop
        Manuskript starting, so a refused entry is logged and dropped.
        """
        for media_type in self.declarations():
            try:
                registry.declare(media_type, USER)
            except Exception as error:
                LOGGER.warning(
                    "Ignoring stored media type %s: %s",
                    getattr(media_type, "id", media_type),
                    error,
                )
        for media_id, target in self.fallbacks().items():
            try:
                registry.assign_fallback(media_id, target)
            except Exception as error:
                LOGGER.warning(
                    "Ignoring stored fallback %s -> %s: %s",
                    media_id,
                    target,
                    error,
                )
        for media_id, target in self.overrides().items():
            try:
                registry.assign_override(media_id, target)
            except Exception as error:
                LOGGER.warning(
                    "Ignoring stored override %s -> %s: %s",
                    media_id,
                    target,
                    error,
                )
        return registry

    def fallbacks(self):
        return self._load(self.FALLBACK_KEY)

    def overrides(self):
        return self._load(self.OVERRIDE_KEY)

    def declarations(self):
        """Media types the user introduced, as MediaType objects."""
        declared = []
        for entry in self._load_list(self.DECLARATION_KEY):
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            try:
                declared.append(MediaType(
                    str(entry["id"]),
                    label=str(entry.get("label", "")),
                    base=str(entry.get("base", "")),
                    textual=bool(entry.get("textual", True)),
                ))
            except MediaTypeError as error:
                LOGGER.warning(
                    "Ignoring stored media type %r: %s", entry, error
                )
        return tuple(declared)

    # ------------------------------------------------------------ storing

    def remember_fallback(self, media_id, target):
        """Record one choice. An empty target forgets it."""
        self._remember(self.FALLBACK_KEY, media_id, target)

    def remember_override(self, media_id, target):
        """Record a remapping. An empty target forgets it."""
        self._remember(self.OVERRIDE_KEY, media_id, target)

    def remember_declaration(self, media_type):
        """Record a format the user introduced, replacing any by that ID."""
        stored = [
            entry
            for entry in self._load_list(self.DECLARATION_KEY)
            if isinstance(entry, dict)
            and str(entry.get("id", "")) != media_type.id
        ]
        stored.append({
            "id": media_type.id,
            "label": media_type.label,
            "base": media_type.base,
            "textual": media_type.textual,
        })
        self._save_list(self.DECLARATION_KEY, stored)

    def forget_declaration(self, media_id):
        media_id = str(media_id)
        self._save_list(self.DECLARATION_KEY, [
            entry
            for entry in self._load_list(self.DECLARATION_KEY)
            if isinstance(entry, dict)
            and str(entry.get("id", "")) != media_id
        ])

    def _remember(self, key, media_id, target):
        stored = self._load(key)
        media_id = str(media_id)
        if target:
            stored[media_id] = str(target)
        else:
            stored.pop(media_id, None)
        self._save(key, stored)

    # -------------------------------------------------------------- plumbing

    def _load(self, key):
        value = self._settings.value(key)
        if value is None:
            return {}
        try:
            decoded = json.loads(str(value))
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring unreadable %s preference.", key)
            return {}
        if not isinstance(decoded, dict):
            return {}
        return {
            str(name): str(target)
            for name, target in decoded.items()
        }

    def _save(self, key, values):
        self._settings.setValue(
            key,
            json.dumps(dict(values), ensure_ascii=False, sort_keys=True),
        )
        self._settings.sync()

    def _load_list(self, key):
        value = self._settings.value(key)
        if value is None:
            return []
        try:
            decoded = json.loads(str(value))
        except (TypeError, ValueError):
            LOGGER.warning("Ignoring unreadable %s preference.", key)
            return []
        return decoded if isinstance(decoded, list) else []

    def _save_list(self, key, values):
        self._settings.setValue(
            key,
            json.dumps(list(values), ensure_ascii=False, sort_keys=True),
        )
        self._settings.sync()


class InMemoryMediaTypePreferences(MediaTypePreferences):
    """The same contract without QSettings, for tests and previews."""

    def __init__(self, fallbacks=None, overrides=None, declarations=None):
        self.values = {
            self.FALLBACK_KEY: dict(fallbacks or {}),
            self.OVERRIDE_KEY: dict(overrides or {}),
            self.DECLARATION_KEY: list(declarations or []),
        }

    def _load(self, key):
        return dict(self.values.get(key, {}))

    def _save(self, key, values):
        self.values[key] = dict(values)

    def _load_list(self, key):
        return list(self.values.get(key, []))

    def _save_list(self, key, values):
        self.values[key] = list(values)
