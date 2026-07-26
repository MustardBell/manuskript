from dataclasses import dataclass

from PyQt5.QtCore import QSettings


@dataclass(frozen=True)
class ApplicationWindowState:
    geometry: object = None
    window_state: object = None
    docks: object = None
    metadata: object = None
    revisions: object = None
    redaction_horizontal: object = None
    redaction_vertical: object = None
    toolbar: object = None


class ApplicationWindowStateStore:
    """Persist opaque Qt window state without knowing any widgets."""

    _KEYS = {
        "geometry": "geometry",
        "window_state": "windowState",
        "docks": "docks",
        "metadata": "metadataState",
        "revisions": "revisionsState",
        "redaction_horizontal": "splitterRedacH",
        "redaction_vertical": "splitterRedacV",
        "toolbar": "toolbar",
    }

    def __init__(self, settings=None):
        self._settings = (
            settings if settings is not None else QSettings()
        )

    def load(self):
        values = {}
        for field, key in self._KEYS.items():
            values[field] = (
                self._settings.value(key)
                if self._settings.contains(key)
                else None
            )
        return ApplicationWindowState(**values)

    def save(self, state):
        for field, key in self._KEYS.items():
            self._settings.setValue(key, getattr(state, field))
        self._settings.sync()
