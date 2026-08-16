"""Going fullscreen belongs to the mode, not to the button.

The fullscreen control is a state switch. When it also decided what
fullscreen meant, a mode it had not been told about got the wrong surface --
or a traceback. These tests hold the boundary: every mode Manuskript ships
answers for itself, and a mode it has never seen still gets a window.
"""

import pytest
from PyQt5.QtWidgets import QLabel, QWidget, qApp

from manuskript.ui.editors.fullscreen_presentation import (
    BorrowedWidgetWindow,
    FullscreenPresentation,
    FullscreenRequest,
    OwnWindow,
    fullscreen_presentation_for,
    register_fullscreen_presentation,
    registered_fullscreen_modes,
)
from manuskript.ui.editors.markdownPresentation import MarkdownPresentationMode


def test_every_shipped_mode_says_how_it_goes_fullscreen():
    registered = registered_fullscreen_modes()

    for mode in MarkdownPresentationMode:
        assert mode.value in registered, mode


def test_the_abstract_answer_is_not_an_answer():
    with pytest.raises(NotImplementedError):
        FullscreenPresentation().enter(
            FullscreenRequest(index=None, settings=None)
        )


def test_a_mode_nobody_has_seen_still_gets_a_window():
    """A plugin need not implement this, and must not be punished for it."""

    presentation = fullscreen_presentation_for("vendor.diagram-mode")

    assert isinstance(presentation, OwnWindow)


def test_a_plugin_mode_may_answer_for_itself():
    class Diagram(FullscreenPresentation):
        def enter(self, request):
            return "taken over"

    register_fullscreen_presentation("vendor.answers", Diagram())

    assert fullscreen_presentation_for("vendor.answers").enter(
        FullscreenRequest(index=None, settings=None)
    ) == "taken over"


def test_the_fallback_window_is_maximized_rather_than_fullscreen():
    """True fullscreen assumes a widget built for it. The floor cannot."""

    home = QWidget()
    borrowed = QLabel("prose", home)
    home.show()
    qApp.processEvents()

    window = BorrowedWidgetWindow(borrowed)
    qApp.processEvents()

    assert window.isMaximized()
    assert not window.isFullScreen()
    window.close()
    qApp.processEvents()


def test_the_window_shows_the_widget_it_was_given_and_gives_it_back():
    home = QWidget()
    borrowed = QLabel("prose", home)
    home.show()
    qApp.processEvents()

    window = BorrowedWidgetWindow(borrowed)
    qApp.processEvents()

    assert borrowed.window() is window

    exits = []
    window.exited.connect(lambda: exits.append(True))
    window.close()
    qApp.processEvents()

    # Borrowed, not taken: the pane it came from must not be left empty.
    assert borrowed.parentWidget() is home
    assert exits == [True]


def test_a_mode_declining_fullscreen_is_not_an_error():
    """OwnWindow has nothing to show without a widget, and says so."""

    assert OwnWindow().enter(
        FullscreenRequest(index=None, settings=None, widget=None)
    ) is None


def test_reading_asks_for_the_surface_in_reading(monkeypatch):
    """The mode on screen is the mode that opens, not a default.

    Entering fullscreen from reading used to reach a surface that then
    renegotiated modes for itself. What a mode passes on is now its own
    identity, which is the whole point of it answering rather than the
    button.
    """

    import manuskript.ui.editors.fullScreenEditor as surface

    built = {}

    def record(index, **kwargs):
        built.update(kwargs)
        return None

    monkeypatch.setattr(surface, "fullScreenEditor", record)

    for mode in MarkdownPresentationMode:
        built.clear()
        fullscreen_presentation_for(mode).enter(
            FullscreenRequest(index=None, settings=None)
        )

        assert built["presentation_mode"] is mode
