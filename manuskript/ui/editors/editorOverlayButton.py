"""Tool buttons that float above editor text.

These controls sit on top of the document rather than in a toolbar, so they
have to stay legible against whatever the writer has typed underneath and
must never resolve to a null icon: the application stylesheet strips tool
button chrome, and an icon-less flat button is an invisible click target.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QToolButton

from manuskript.ui import style as S


#: Height reserved above the document so text never runs under the buttons.
OVERLAY_HEIGHT = 28
OVERLAY_MARGIN = 4


def overlay_icon(names, fallback):
    """First icon the current theme actually provides, never null.

    Icon themes vary by platform and several names Manuskript would like
    are missing from the bundled theme, so fall back to a Qt standard
    pixmap rather than letting the button render as empty space.
    """
    for name in names:
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return QApplication.style().standardIcon(fallback)


class EditorOverlayToolButton(QToolButton):
    """Base chrome for a tool button drawn over the document."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAutoRaise(False)
        self.setStyleSheet(S.editorOverlayButtonSS())
