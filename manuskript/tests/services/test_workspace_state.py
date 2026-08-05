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
