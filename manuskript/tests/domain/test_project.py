import pytest

from manuskript.domain.project import (
    InvalidProjectStateTransition,
    ProjectSession,
    ProjectState,
)


def test_new_session_is_closed():
    session = ProjectSession()

    assert session.state is ProjectState.CLOSED
    assert session.path is None
    assert not session.is_open
    assert not session.is_dirty


def test_session_tracks_clean_and_dirty_project_states():
    session = ProjectSession()

    session.open("/tmp/story.msk")
    assert session.state is ProjectState.CLEAN
    assert session.path == "/tmp/story.msk"
    assert session.is_open
    assert not session.is_dirty

    session.mark_dirty()
    assert session.state is ProjectState.DIRTY
    assert session.is_dirty

    session.mark_clean()
    assert session.state is ProjectState.CLEAN

    session.close()
    assert session.state is ProjectState.CLOSED
    assert session.path is None


def test_session_rejects_operations_without_an_open_project():
    session = ProjectSession()

    with pytest.raises(InvalidProjectStateTransition):
        session.mark_dirty()
    with pytest.raises(InvalidProjectStateTransition):
        session.mark_clean()
    with pytest.raises(InvalidProjectStateTransition):
        session.rename("/tmp/renamed.msk")


def test_session_rejects_opening_a_second_project():
    session = ProjectSession()
    session.open("/tmp/first.msk")

    with pytest.raises(InvalidProjectStateTransition):
        session.open("/tmp/second.msk")

    assert session.path == "/tmp/first.msk"
    assert session.state is ProjectState.CLEAN


def test_session_rename_preserves_dirty_state():
    session = ProjectSession()
    session.open("/tmp/first.msk")
    session.mark_dirty()

    session.rename("/tmp/renamed.msk")

    assert session.path == "/tmp/renamed.msk"
    assert session.state is ProjectState.DIRTY
