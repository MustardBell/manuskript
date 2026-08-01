import pytest

from manuskript.domain.theme import (
    InvalidThemeEditorTransition,
    ThemeEditorSession,
    ThemeEditorState,
)


def test_theme_editor_session_owns_edit_transaction_state():
    session = ThemeEditorSession()

    session.start("custom.theme", {"Name": "Custom"})
    session.update("Name", "Renamed")

    assert session.state is ThemeEditorState.EDITING
    assert session.path == "custom.theme"
    assert session.data == {"Name": "Renamed"}

    session.finish()

    assert session.state is ThemeEditorState.BROWSING
    assert session.path is None
    assert session.data is None


def test_theme_editor_session_rejects_invalid_transitions():
    session = ThemeEditorSession()

    with pytest.raises(InvalidThemeEditorTransition):
        session.finish()

    session.start("custom.theme", {})
    with pytest.raises(InvalidThemeEditorTransition):
        session.start("other.theme", {})

    session.cancel()
    assert not session.is_editing
