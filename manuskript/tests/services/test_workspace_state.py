"""Layout is filed per window, and panels by identity.

Two failures the old fixed-key store made possible, both silent:
a second window saving its layout over the first's, and a panel losing
its visibility because the text on its button changed.
"""

from PyQt5.QtCore import QSettings

from manuskript.services.workspace_state import (
    PRIMARY,
    WORKSPACE_STATE_VERSION,
    WorkspaceStateStore,
    WorkspaceWindowState,
    as_bool,
)


def store(tmp_path, name="workspace.ini"):
    settings = QSettings(
        str(tmp_path / name), QSettings.IniFormat,
    )
    return WorkspaceStateStore(settings), settings


def test_a_layout_round_trips(tmp_path):
    subject, _settings = store(tmp_path)
    state = WorkspaceWindowState(
        geometry=b"geo",
        window_state=b"docks",
        splitters={"splitterRedacH": b"sizes"},
        panels={"core.metadata": True, "core.storyline": False},
        panel_state={"core.metadata": [True, False]},
        docks={"dckSearch": True},
        surfaces=("core.general", "core.editor"),
        active_surface="core.editor",
    )

    subject.save(state, PRIMARY)
    loaded = subject.load(PRIMARY)

    assert loaded.geometry == b"geo"
    assert loaded.window_state == b"docks"
    assert loaded.splitters["splitterRedacH"] == b"sizes"
    assert loaded.panels == {
        "core.metadata": True, "core.storyline": False,
    }
    assert loaded.docks == {"dckSearch": True}
    assert loaded.surfaces == ("core.general", "core.editor")
    assert loaded.active_surface == "core.editor"


def test_pre_membership_layout_is_distinct_from_an_explicit_set(tmp_path):
    subject, _settings = store(tmp_path)

    assert subject.load(PRIMARY).surfaces is None

    subject.save(WorkspaceWindowState(surfaces=("core.editor",)), PRIMARY)

    assert subject.load(PRIMARY).surfaces == ("core.editor",)


def test_unreadable_surface_membership_is_ignored(tmp_path):
    subject, settings = store(tmp_path)
    key = "workspace/windows/main/surfaces"

    settings.setValue(key, '{"core.editor": true}')

    assert subject.load(PRIMARY).surfaces is None


def test_saving_surface_identity_removes_the_keys_it_replaced(tmp_path):
    """Two keys stop being written, for the same reason.

    The tab number was a position; the active panel was two facts under
    one name, and could say "project tree" -- a tool panel no navigator
    row stands for. Both remain readable as migration inputs, which is
    why they have to be cleared rather than merely ignored: left behind,
    the next load would keep preferring them.
    """

    subject, settings = store(tmp_path)
    settings.setValue("workspace/windows/main/mainTab", 6)
    settings.setValue("workspace/windows/main/activePanel", "core.metadata")

    subject.save(
        WorkspaceWindowState(active_surface="core.editor"), PRIMARY,
    )

    assert not settings.contains("workspace/windows/main/mainTab")
    assert not settings.contains("workspace/windows/main/activePanel")
    assert subject.load(PRIMARY).active_surface == "core.editor"


def test_two_windows_do_not_overwrite_each_other(tmp_path):
    """The whole reason for the new shape."""
    subject, _settings = store(tmp_path)

    subject.save(
        WorkspaceWindowState(geometry=b"first"), PRIMARY,
    )
    subject.save(
        WorkspaceWindowState(geometry=b"second"), "window-2",
    )

    assert subject.load(PRIMARY).geometry == b"first"
    assert subject.load("window-2").geometry == b"second"
    assert subject.window_ids() == (PRIMARY, "window-2")


def test_the_primary_window_is_listed_first(tmp_path):
    subject, _settings = store(tmp_path)
    subject.save(WorkspaceWindowState(), "window-3")
    subject.save(WorkspaceWindowState(), "window-2")
    subject.save(WorkspaceWindowState(), PRIMARY)

    assert subject.window_ids() == (PRIMARY, "window-2", "window-3")


def test_an_unknown_window_loads_as_empty_rather_than_failing(tmp_path):
    subject, _settings = store(tmp_path)

    state = subject.load("window-never-opened")

    assert state.geometry is None
    assert state.panels == {}
    assert state.splitters == {}


def test_forgetting_a_window_leaves_the_others(tmp_path):
    subject, _settings = store(tmp_path)
    subject.save(WorkspaceWindowState(geometry=b"first"), PRIMARY)
    subject.save(WorkspaceWindowState(geometry=b"second"), "window-2")

    subject.forget("window-2")

    assert subject.window_ids() == (PRIMARY,)
    assert subject.load(PRIMARY).geometry == b"first"


def test_a_hidden_panel_stays_hidden_across_an_ini_round_trip(tmp_path):
    """An INI backend hands back the string "false", which is true to
    Python -- the kind of quiet wrongness that reopens a panel somebody
    closed.
    """
    subject, settings = store(tmp_path)
    subject.save(
        WorkspaceWindowState(panels={"core.metadata": False}), PRIMARY,
    )
    settings.sync()

    reopened = WorkspaceStateStore(
        QSettings(settings.fileName(), QSettings.IniFormat)
    )

    assert reopened.load(PRIMARY).panels == {"core.metadata": False}


def test_removed_panels_do_not_linger(tmp_path):
    """Saving replaces a window's panel set rather than merging into
    it, so a panel that is gone does not come back.
    """
    subject, _settings = store(tmp_path)
    subject.save(
        WorkspaceWindowState(panels={
            "core.metadata": True, "plugin.old.panel": True,
        }),
        PRIMARY,
    )

    subject.save(
        WorkspaceWindowState(panels={"core.metadata": True}), PRIMARY,
    )

    assert subject.load(PRIMARY).panels == {"core.metadata": True}


def test_the_stored_shape_records_its_version(tmp_path):
    subject, settings = store(tmp_path)

    subject.save(WorkspaceWindowState(), PRIMARY)

    assert int(settings.value("workspace/version")) == (
        WORKSPACE_STATE_VERSION
    )


def test_as_bool_reads_what_qsettings_meant():
    for value in ("false", "False", "0", "", "  ", "no", None, 0):
        assert as_bool(value) is False, value
    for value in ("true", "True", "1", "yes", 1, True):
        assert as_bool(value) is True, value


# ----------------------------------------------------- session windows

def test_the_session_records_which_windows_were_open(tmp_path):
    subject, _settings = store(tmp_path)

    subject.set_open_windows([PRIMARY, "window-2"])

    assert subject.open_windows() == (PRIMARY, "window-2")


def test_no_recorded_session_is_empty_rather_than_a_guess(tmp_path):
    """A first launch has no session. Assuming one window would be a
    guess; the caller already has its own window.
    """
    subject, _settings = store(tmp_path)

    assert subject.open_windows() == ()


def test_a_single_recorded_window_survives_an_ini_round_trip(tmp_path):
    """QSettings collapses a one-item list to a bare string, which
    would otherwise come back as a list of its characters.
    """
    subject, settings = store(tmp_path)
    subject.set_open_windows([PRIMARY])
    settings.sync()

    reopened = WorkspaceStateStore(
        QSettings(settings.fileName(), QSettings.IniFormat)
    )

    assert reopened.open_windows() == (PRIMARY,)


def test_layout_for_windows_the_session_dropped_is_forgotten(tmp_path):
    """Otherwise every window ever opened leaves a stanza behind that
    nothing will read again.
    """
    subject, _settings = store(tmp_path)
    subject.save(WorkspaceWindowState(geometry=b"one"), PRIMARY)
    subject.save(WorkspaceWindowState(geometry=b"two"), "window-2")
    subject.save(WorkspaceWindowState(geometry=b"three"), "window-3")

    subject.set_open_windows([PRIMARY, "window-2"])

    assert subject.window_ids() == (PRIMARY, "window-2")
    assert subject.load(PRIMARY).geometry == b"one"
    assert subject.load("window-2").geometry == b"two"


def test_the_primary_window_keeps_its_layout_regardless(tmp_path):
    """It is always the window that opens next, so its layout is never
    the one to discard.
    """
    subject, _settings = store(tmp_path)
    subject.save(WorkspaceWindowState(geometry=b"main"), PRIMARY)

    subject.set_open_windows(["window-2"])

    assert subject.load(PRIMARY).geometry == b"main"


# --------------------------------------------------- open documents

def test_open_documents_keep_their_nested_shape(tmp_path):
    """A split layout is a nested, mixed-type structure. QSettings would
    flatten it into unrecognisable strings, so it is stored as JSON.
    """
    subject, settings = store(tmp_path)
    documents = [1, ["scene-1", "scene-2"], [0, ["scene-3"], None]]

    subject.save(WorkspaceWindowState(documents=documents), PRIMARY)
    settings.sync()
    reopened = WorkspaceStateStore(
        QSettings(settings.fileName(), QSettings.IniFormat)
    )

    assert reopened.load(PRIMARY).documents == documents


def test_two_windows_remember_different_documents(tmp_path):
    """Two windows on one project are two places to be reading."""
    subject, _settings = store(tmp_path)

    subject.save(WorkspaceWindowState(documents=[0, ["a"], None]), PRIMARY)
    subject.save(
        WorkspaceWindowState(documents=[0, ["b"], None]), "window-2",
    )

    assert subject.load(PRIMARY).documents == [0, ["a"], None]
    assert subject.load("window-2").documents == [0, ["b"], None]


def test_never_recorded_documents_differ_from_recorded_none(tmp_path):
    """None tells the caller to fall back to what the project
    remembers; an empty list tells it to open nothing.
    """
    subject, _settings = store(tmp_path)
    subject.save(WorkspaceWindowState(), PRIMARY)

    assert subject.load(PRIMARY).documents is None

    subject.save(WorkspaceWindowState(documents=[0, [], None]), PRIMARY)

    assert subject.load(PRIMARY).documents == [0, [], None]


def test_unreadable_documents_are_ignored_not_raised(tmp_path):
    """Corrupted text must not stop somebody opening their project."""
    subject, settings = store(tmp_path)
    settings.setValue(
        "workspace/windows/main/documents", "{not json",
    )

    assert subject.load(PRIMARY).documents is None
