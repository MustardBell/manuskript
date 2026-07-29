from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QToolButton

from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


class MarkdownModeToolButton(QToolButton):
    """Leaf-local mode control whose icon describes the click target."""

    _MODE_LABELS = {
        MarkdownPresentationMode.SOURCE: "Source",
        MarkdownPresentationMode.FORMATTED_SOURCE: "Formatted Source",
        MarkdownPresentationMode.LIVE_PREVIEW: "Live Preview",
        MarkdownPresentationMode.READING: "Reading",
    }

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._lastEditableMode = MarkdownPresentationMode.LIVE_PREVIEW
        self._actions = {}

        self.setObjectName("markdownModeToolButton")
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setPopupMode(QToolButton.MenuButtonPopup)

        menu = QMenu(self)
        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        for mode in MarkdownPresentationMode:
            action = QAction(self._MODE_LABELS[mode], self)
            action.setCheckable(True)
            action.setActionGroup(action_group)
            action.triggered.connect(
                lambda _checked=False, selected_mode=mode:
                    self._state.set_mode(selected_mode)
            )
            menu.addAction(action)
            self._actions[mode] = action
        self.setMenu(menu)

        self.clicked.connect(self.toggleReading)
        state.modeChanged.connect(self.syncMode)
        self.syncMode(state.mode)

    @property
    def presentationState(self):
        return self._state

    def toggleReading(self):
        if self._state.mode is MarkdownPresentationMode.READING:
            self._state.set_mode(self._lastEditableMode)
        else:
            self._state.set_mode(MarkdownPresentationMode.READING)

    def syncMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if mode.is_editable:
            self._lastEditableMode = mode
            target_mode = MarkdownPresentationMode.READING
            icon = QIcon.fromTheme(
                "view-preview",
                QIcon.fromTheme("document-preview"),
            )
        else:
            target_mode = self._lastEditableMode
            icon = QIcon.fromTheme(
                "document-edit",
                QIcon.fromTheme("accessories-text-editor"),
            )

        self.setIcon(icon)
        self.setToolTip(
            self.tr("Switch to {}").format(
                self._MODE_LABELS[target_mode]
            )
        )
        self._actions[mode].setChecked(True)
