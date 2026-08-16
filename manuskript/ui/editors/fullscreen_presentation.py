"""How a presentation mode takes over the screen.

The fullscreen control is a state switch and knows nothing about modes. What
"fullscreen" means belongs to the mode being shown: a source editor wants the
distraction-free surface with its own themes, a rendered reading view wants
its rendering at full size, and a mode contributed by a plugin wants whatever
that plugin's widget already is.

So each mode answers for itself. Every mode Manuskript ships names its
behaviour explicitly -- there is no default for them, and a test refuses a
mode that has not said. A mode contributed by a plugin may name one too, and
if it does not it still gets the floor every mode is guaranteed: its own
maximized top-level window. Deliberately maximized rather than truly
fullscreen -- true fullscreen wants a widget that has been built for it, and
the floor has to be something any widget can be given sight unseen. The modes
Manuskript ships do go truly fullscreen, because they were built for it.
"""

from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from manuskript.ui.editors.markdownPresentation import MarkdownPresentationMode


@dataclass(frozen=True)
class FullscreenRequest:
    """Everything a mode may need to show itself at full size."""

    index: Any
    settings: Any
    widget: Optional[QWidget] = None
    text_editor_context: Any = None
    markup_profile: Any = None
    screen_number: Optional[int] = None


class FullscreenPresentation:
    """What every presentation mode must be able to answer.

    ``enter`` returns an object carrying an ``exited`` signal, or None if the
    mode declines. It must never assume the caller knew which mode it was:
    that assumption is the one this replaces.
    """

    def enter(self, request):
        raise NotImplementedError(
            "A presentation mode must say how it goes fullscreen."
        )


class BorrowedWidgetWindow(QWidget):
    """A widget shown in its own maximized window, then given back.

    This is the floor rather than the ideal: no theme, no chrome, no
    knowledge of what is inside, and maximized rather than truly fullscreen
    because a widget built for neither survives the first better than the
    second. It works for any widget at all, which is what makes it a promise
    that can be made to a mode nobody has seen.
    """

    exited = pyqtSignal()

    def __init__(self, widget, screen_number=None):
        super().__init__(None)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._widget = widget
        self._home = widget.parentWidget()
        self._home_geometry = widget.geometry()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        self.setWindowTitle(self.tr("Manuskript"))
        self.showMaximized()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # The widget was borrowed, not taken: an editor still owns it, and
        # leaving it parented here would blank the pane it came from.
        if self._widget is not None and self._home is not None:
            self._widget.setParent(self._home)
            self._widget.setGeometry(self._home_geometry)
            self._widget.show()
        self._widget = None
        self.exited.emit()
        super().closeEvent(event)


class OwnWindow(FullscreenPresentation):
    """The guaranteed minimum: this mode's widget, in a maximized window."""

    def enter(self, request):
        if request.widget is None:
            return None
        return BorrowedWidgetWindow(request.widget, request.screen_number)


class DistractionFreeEditor(FullscreenPresentation):
    """The themed writing surface, built around a fresh editor."""

    def __init__(self, mode):
        self.mode = mode

    def enter(self, request):
        # Imported here: the distraction-free surface pulls in themes and
        # editor machinery that this module's contract does not need.
        from manuskript.ui.editors.fullScreenEditor import fullScreenEditor

        return fullScreenEditor(
            request.index,
            settings=request.settings,
            text_editor_context=request.text_editor_context,
            screenNumber=request.screen_number,
            presentation_mode=self.mode,
            markup_profile=request.markup_profile,
        )


_REGISTRY = {}


def register_fullscreen_presentation(mode, presentation):
    """Say how one mode goes fullscreen, by mode or by its plain value."""

    _REGISTRY[_key(mode)] = presentation


def fullscreen_presentation_for(mode):
    """The behaviour for a mode, falling back to the guaranteed window."""

    return _REGISTRY.get(_key(mode), OwnWindow())


def registered_fullscreen_modes():
    return frozenset(_REGISTRY)


def _key(mode):
    return getattr(mode, "value", str(mode))


# Every shipped mode names its own behaviour. Sharing an implementation is
# allowed; leaving the question unanswered is not.
for _mode in (
    MarkdownPresentationMode.SOURCE,
    MarkdownPresentationMode.FORMATTED_SOURCE,
    MarkdownPresentationMode.LIVE_PREVIEW,
    MarkdownPresentationMode.CLEAN_EDITING,
    MarkdownPresentationMode.READING,
):
    register_fullscreen_presentation(_mode, DistractionFreeEditor(_mode))
