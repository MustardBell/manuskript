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


LOGGER = logging.getLogger(__name__)


class MediaTypePreferences:
    """Load and store the user's media type choices for a registry."""

    FALLBACK_KEY = "media-types/fallbacks"

    def __init__(self, settings=None):
        self._settings = (
            settings if settings is not None else QSettings()
        )

    # ------------------------------------------------------------ loading

    def apply(self, registry):
        """Put stored choices into a registry, skipping ones it refuses.

        A stored fallback can be stale -- the format it named may have gone
        with an uninstalled plugin, and a pair that was fine when saved can
        close a loop once other choices change. Neither should stop
        Manuskript starting, so a refused entry is logged and dropped.
        """
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
        return registry

    def fallbacks(self):
        return self._load(self.FALLBACK_KEY)

    # ------------------------------------------------------------ storing

    def remember_fallback(self, media_id, target):
        """Record one choice. An empty target forgets it."""
        stored = self.fallbacks()
        media_id = str(media_id)
        if target:
            stored[media_id] = str(target)
        else:
            stored.pop(media_id, None)
        self._save(self.FALLBACK_KEY, stored)

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


class InMemoryMediaTypePreferences(MediaTypePreferences):
    """The same contract without QSettings, for tests and previews."""

    def __init__(self, fallbacks=None):
        self.values = {self.FALLBACK_KEY: dict(fallbacks or {})}

    def _load(self, key):
        return dict(self.values.get(key, {}))

    def _save(self, key, values):
        self.values[key] = dict(values)
