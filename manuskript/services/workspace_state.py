"""Where each workspace window's layout is remembered.

The old store wrote eight fixed keys -- ``geometry``, ``windowState``,
``splitterRedacH`` and so on -- which was fine while there was one
window and wrong the moment there were two: the second would save its
layout over the first's.

State is now filed under a window identifier, and panels are recorded by
panel id rather than by the text on their button. Matching on button
text meant a renamed or translated panel silently lost its visibility.

This is a new model rather than a wider version of the old one, and it
carries its own version so later shapes can be migrated rather than
guessed at. :mod:`manuskript.preferences_migrations` moves the legacy
keys into it, and legacy spelling appears nowhere else.
"""

from dataclasses import dataclass, field

from PyQt5.QtCore import QSettings


#: Bump when the stored shape changes, and add a migration step.
WORKSPACE_STATE_VERSION = 1

#: Everything this module owns lives under here.
ROOT = "workspace"

#: The identifier of the window a single-window session used.
PRIMARY = "main"


@dataclass(frozen=True)
class WorkspaceWindowState:
    """One window's layout, as opaque payloads and plain booleans."""

    geometry: object = None
    window_state: object = None
    #: Splitter name -> saved sizes.
    splitters: dict = field(default_factory=dict)
    #: Panel id -> whether it was showing.
    panels: dict = field(default_factory=dict)
    #: Panel id -> that panel's own saved state.
    panel_state: dict = field(default_factory=dict)
    #: Dock objectName -> whether it was showing.
    docks: dict = field(default_factory=dict)


class WorkspaceStateStore:
    """Read and write per-window layout, knowing no widgets."""

    def __init__(self, settings=None):
        self._settings = (
            settings if settings is not None else QSettings()
        )

    # ------------------------------------------------------------ paths

    def _window_root(self, window_id):
        return "{}/windows/{}".format(ROOT, window_id)

    def _key(self, window_id, *parts):
        return "/".join((self._window_root(window_id),) + parts)

    # ------------------------------------------------------------- read

    def window_ids(self):
        """Every window with saved state, primary first."""
        self._settings.beginGroup("{}/windows".format(ROOT))
        try:
            found = list(self._settings.childGroups())
        finally:
            self._settings.endGroup()
        found.sort(key=lambda name: (name != PRIMARY, name))
        return tuple(found)

    def load(self, window_id=PRIMARY):
        return WorkspaceWindowState(
            geometry=self._value(window_id, "geometry"),
            window_state=self._value(window_id, "windowState"),
            splitters=self._group(window_id, "splitters"),
            panels=self._flags(window_id, "panels"),
            panel_state=self._group(window_id, "panelState"),
            docks=self._flags(window_id, "docks"),
        )

    def save(self, state, window_id=PRIMARY):
        self._settings.setValue(
            "{}/version".format(ROOT),
            WORKSPACE_STATE_VERSION,
        )
        self._set(window_id, "geometry", state.geometry)
        self._set(window_id, "windowState", state.window_state)
        self._write_group(window_id, "splitters", state.splitters)
        self._write_group(window_id, "panels", state.panels)
        self._write_group(window_id, "panelState", state.panel_state)
        self._write_group(window_id, "docks", state.docks)
        self._settings.sync()

    def forget(self, window_id):
        """Drop one window's state, for a window not coming back."""
        self._settings.remove(self._window_root(window_id))
        self._settings.sync()

    # ------------------------------------------------- session windows

    def open_windows(self):
        """The windows a previous session had open, primary first.

        Saved layout is not the same question: a window can have a
        remembered size without having been open at the end.
        """
        key = "{}/openWindows".format(ROOT)
        stored = (
            self._settings.value(key)
            if self._settings.contains(key)
            else None
        )
        if stored is None:
            return ()
        if isinstance(stored, str):
            stored = [stored] if stored else []
        found = [str(entry) for entry in stored if str(entry)]
        found.sort(key=lambda name: (name != PRIMARY, name))
        return tuple(found)

    def set_open_windows(self, window_ids):
        window_ids = [str(entry) for entry in window_ids]
        self._settings.setValue(
            "{}/openWindows".format(ROOT),
            window_ids,
        )
        self.forget_windows_except(window_ids)
        self._settings.sync()

    def forget_windows_except(self, window_ids):
        """Drop layout for windows the session did not end with.

        Otherwise every window ever opened accumulates a stanza that
        nothing will read again, and the primary's is never among the
        casualties.
        """
        keep = set(window_ids) | {PRIMARY}
        for window_id in self.window_ids():
            if window_id not in keep:
                self._settings.remove(self._window_root(window_id))

    # ----------------------------------------------------------- pieces

    def _value(self, window_id, name):
        key = self._key(window_id, name)
        return (
            self._settings.value(key)
            if self._settings.contains(key)
            else None
        )

    def _set(self, window_id, name, value):
        self._settings.setValue(self._key(window_id, name), value)

    def _group(self, window_id, name):
        self._settings.beginGroup(self._key(window_id, name))
        try:
            return {
                key: self._settings.value(key)
                for key in self._settings.childKeys()
            }
        finally:
            self._settings.endGroup()

    def _flags(self, window_id, name):
        """A group of booleans, however QSettings spelled them.

        An INI backend hands back the string "false", which is true to
        Python -- exactly the kind of quiet wrongness that turns a
        hidden panel into a visible one on the next launch.
        """
        return {
            key: as_bool(value)
            for key, value in self._group(window_id, name).items()
        }

    def _write_group(self, window_id, name, values):
        root = self._key(window_id, name)
        self._settings.remove(root)
        for key, value in (values or {}).items():
            self._settings.setValue("{}/{}".format(root, key), value)


def as_bool(value):
    """What QSettings gave back, as the boolean it meant."""
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no")
    return bool(value)
