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

import json
import logging

from dataclasses import dataclass, field

from PyQt5.QtCore import QSettings


LOGGER = logging.getLogger(__name__)


#: Bump when the stored shape changes, and add a migration step.
#:
#: 2 -- the entity docks were first placed tabbed over one another and
#: that arrangement was saved, so a layout written by 1 has to be laid
#: out once more rather than leaving people with tabs they never chose.
#: 3 -- the last central story tab became a stable panel identity. The old
#: integer is still read once so existing workspaces reopen where they were.
#: 4 -- "which panel was active" split in two. The surface a window was
#: showing is filed under activeSurface; the old key could name a tool
#: panel that no navigator row stands for, and is read once as a migration
#: input.
#: 5 -- workspace surface membership became explicit. A missing surfaces
#: key is the pre-v5 canonical workspace; a stored list is the exact subset
#: that window owned when the session ended.
#: 6 -- visibility of surface-routed tool panels is interpreted as the
#: reader's choice for the saved active surface. Earlier versions always
#: opened the project tree globally, so their saved ``true`` is an obsolete
#: default rather than evidence that it was requested on General or Outline.
#: 7 -- tool-panel membership became explicit alongside surface membership.
#: A missing toolPanels key is migrated from the workspace's surface shape;
#: an empty list is the valid answer for a sparse surface-only workspace.
#:
#: The version says what shape the stored keys are in, and nothing else.
#: Whether an arrangement of docks may be applied is not asked here and is
#: not asked of this number: the window that would apply it asks the
#: layout what it contains, because a version answers that wrongly for the
#: readers who matter most -- one upgrading from upstream arrives stamped
#: 1 with a layout naming no work-surface docks at all.
WORKSPACE_STATE_VERSION = 7

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
    # ---- this window's view of the project ----
    # Both are None when this window has never recorded them, which is
    # not the same as having recorded nothing: the first says to fall
    # back to what the project remembers, the second is an answer.

    #: Which documents this window had open, in its own split layout.
    documents: object = None
    #: Ordered surface ids this window owned. None means pre-v5 state.
    surfaces: object = None
    #: Ordered tool-panel ids this window owned. None means pre-v7 state.
    tool_panels: object = None
    #: Legacy tab index, read only as a migration input for pre-v3 layouts.
    main_tab: object = None
    #: Which work surface this window was showing, from the surface host.
    active_surface: object = None
    #: Whatever last held this window's semantic focus, which may be a
    #: tool panel. Read only as a migration input: it was written as
    #: though it were the active surface, so a layout from before the two
    #: were told apart can say "project tree" here.
    active_panel: object = None


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
            documents=self._json(window_id, "documents"),
            surfaces=self._string_tuple(window_id, "surfaces"),
            tool_panels=self._string_tuple(window_id, "toolPanels"),
            main_tab=self._int(window_id, "mainTab"),
            active_surface=self._string(window_id, "activeSurface"),
            active_panel=self._string(window_id, "activePanel"),
        )

    def stored_version(self):
        """Which version of this application last wrote a layout.

        Zero when nothing has been saved yet. Read so an arrangement
        that a later version would no longer produce can be corrected
        once, instead of being inherited for good.
        """
        value = self._settings.value("{}/version".format(ROOT), 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

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
        self._set_json(window_id, "documents", state.documents)
        self._set_json(window_id, "surfaces", state.surfaces)
        self._set_json(window_id, "toolPanels", state.tool_panels)
        # Stop writing the tab-era key. It remains readable above as a
        # migration input, including from project settings in old files.
        self._settings.remove(self._key(window_id, "mainTab"))
        # Likewise the key that meant two things at once. What is written
        # now is the surface the window was showing; whatever last had
        # focus is this session's business and nobody's next launch.
        self._settings.remove(self._key(window_id, "activePanel"))
        self._set_optional(window_id, "activeSurface", state.active_surface)
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

    def _json(self, window_id, name):
        """A stored structure, read back as itself.

        Open documents are a nested, mixed-type structure -- a split
        state, a list of ids, and possibly another of the same -- which
        QSettings would flatten into unrecognisable strings. JSON keeps
        the shape, and unreadable text is treated as nothing recorded
        rather than allowed to raise on somebody's next launch.
        """
        stored = self._value(window_id, name)
        if stored is None:
            return None
        try:
            return json.loads(str(stored))
        except (TypeError, ValueError):
            LOGGER.warning(
                "Ignoring unreadable %s for window %s.", name, window_id,
            )
            return None

    def _set_json(self, window_id, name, value):
        if value is None:
            self._settings.remove(self._key(window_id, name))
            return
        self._set(window_id, name, json.dumps(value))

    def _string_tuple(self, window_id, name):
        """A JSON list of stable ids, or None when absent/unreadable."""

        value = self._json(window_id, name)
        if value is None:
            return None
        if not isinstance(value, list):
            LOGGER.warning(
                "Ignoring non-list %s for window %s.", name, window_id,
            )
            return None
        found = []
        for entry in value:
            if not isinstance(entry, str):
                LOGGER.warning(
                    "Ignoring non-string entry in %s for window %s.",
                    name,
                    window_id,
                )
                continue
            entry = entry.strip()
            if entry and entry not in found:
                found.append(entry)
        return tuple(found)

    def _int(self, window_id, name):
        """A stored whole number, or None when never recorded."""
        stored = self._value(window_id, name)
        if stored is None:
            return None
        try:
            return int(stored)
        except (TypeError, ValueError):
            LOGGER.warning(
                "Ignoring unreadable %s for window %s.", name, window_id,
            )
            return None

    def _string(self, window_id, name):
        stored = self._value(window_id, name)
        if stored is None:
            return None
        value = str(stored).strip()
        return value or None

    def _set_optional(self, window_id, name, value):
        if value is None:
            self._settings.remove(self._key(window_id, name))
            return
        self._set(window_id, name, value)

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
