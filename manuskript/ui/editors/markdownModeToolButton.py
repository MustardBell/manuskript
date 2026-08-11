from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QStyle

from manuskript.ui.editors.editorOverlayButton import (
    EditorOverlayToolButton,
    overlay_icon,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


class MarkdownModeToolButton(EditorOverlayToolButton):
    """Leaf-local mode control whose icon describes the click target."""

    _MODE_LABELS = {
        MarkdownPresentationMode.SOURCE: "Source",
        MarkdownPresentationMode.FORMATTED_SOURCE: "Formatted Source",
        MarkdownPresentationMode.LIVE_PREVIEW: "Live Preview",
        MarkdownPresentationMode.CLEAN_EDITING: "Clean Editing",
        MarkdownPresentationMode.READING: "Reading",
    }

    # NumixMsk ships none of the obvious freedesktop names for these,
    # so each entry ends in a Qt standard pixmap that always resolves.
    _READING_ICON = (
        ("view-text", "view-preview", "document-preview", "text-html"),
        QStyle.SP_FileDialogContentsView,
    )
    _EDIT_ICON = (
        ("document-edit", "gtk-edit", "accessories-text-editor"),
        QStyle.SP_FileDialogDetailedView,
    )
    _SOURCE_ICON = (
        ("code-context", "text-x-markdown", "text-x-script",
         "text-plain"),
        QStyle.SP_FileIcon,
    )

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self._state = state
        self._lastEditableMode = MarkdownPresentationMode.LIVE_PREVIEW
        self._actions = {}

        self.setObjectName("markdownModeToolButton")
        self.setPopupMode(self.MenuButtonPopup)

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
        state.allowedModesChanged.connect(self.syncAllowedModes)
        self.syncAllowedModes(state.allowed_modes)
        self.syncMode(state.mode)

    @property
    def presentationState(self):
        return self._state

    def toggleReading(self):
        if MarkdownPresentationMode.READING in self._state.allowed_modes:
            if self._state.mode is MarkdownPresentationMode.READING:
                self._state.set_mode(self._lastEditableMode)
            else:
                self._state.set_mode(MarkdownPresentationMode.READING)
        else:
            target = (
                MarkdownPresentationMode.SOURCE
                if self._state.mode
                is MarkdownPresentationMode.FORMATTED_SOURCE
                else MarkdownPresentationMode.FORMATTED_SOURCE
            )
            self._state.set_mode(target)

    def syncMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if (
            mode.is_editable
            and MarkdownPresentationMode.READING
            in self._state.allowed_modes
        ):
            self._lastEditableMode = mode
            target_mode = MarkdownPresentationMode.READING
            icon = overlay_icon(*self._READING_ICON)
        elif mode is MarkdownPresentationMode.READING:
            target_mode = self._lastEditableMode
            icon = overlay_icon(*self._EDIT_ICON)
        else:
            target_mode = (
                MarkdownPresentationMode.SOURCE
                if mode is MarkdownPresentationMode.FORMATTED_SOURCE
                else MarkdownPresentationMode.FORMATTED_SOURCE
            )
            icon = overlay_icon(*self._SOURCE_ICON)

        self.setIcon(icon)
        self.setToolTip(
            self.tr("Switch to {}").format(
                self._MODE_LABELS[target_mode]
            )
        )
        self._actions[mode].setChecked(True)

    def syncAllowedModes(self, modes):
        allowed = set(modes)
        for mode, action in self._actions.items():
            action.setEnabled(mode in allowed)
        self.syncMode(self._state.mode)
