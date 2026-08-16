from PyQt5.QtWidgets import QAction, QActionGroup, QMenu, QStyle

from manuskript.ui.editors.editorOverlayButton import (
    EditorOverlayToolButton,
    overlay_icon,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)


class MarkdownModeToolButton(EditorOverlayToolButton):
    """Leaf-local mode control whose icon describes the click target.

    Clicking cycles to the next mode this leaf allows, in the order it was
    given them, and wraps. It deliberately does not toggle between two modes
    it was told to care about: which modes exist, and in what order, is not
    this button's to know. A plugin may add a mode, remove one, or reorder
    them, and a control built around a favourite pair would quietly stop
    reaching whatever it had not been told about.

    The menu is rebuilt from the same list, so it offers exactly the modes
    that are available and nothing else.
    """

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
        self._actions = {}

        self.setObjectName("markdownModeToolButton")
        self.setPopupMode(self.MenuButtonPopup)
        self.setMenu(QMenu(self))

        self.clicked.connect(self.cycleMode)
        state.modeChanged.connect(self.syncMode)
        state.allowedModesChanged.connect(self.syncAllowedModes)
        self.syncAllowedModes(state.allowed_modes)

    @property
    def presentationState(self):
        return self._state

    @classmethod
    def labelFor(cls, mode):
        """What to call a mode, including one this build has never seen."""

        if mode in cls._MODE_LABELS:
            return cls._MODE_LABELS[mode]
        value = getattr(mode, "value", str(mode))
        return str(value).replace("-", " ").replace("_", " ").title()

    def nextMode(self):
        """The mode a click moves to: the following one, wrapping round."""

        allowed = tuple(self._state.allowed_modes)
        if not allowed:
            return None
        try:
            position = allowed.index(self._state.mode)
        except ValueError:
            # The current mode is not on offer here, so the first one that
            # is stands as the next.
            return allowed[0]
        return allowed[(position + 1) % len(allowed)]

    def cycleMode(self):
        target = self.nextMode()
        if target is not None and target is not self._state.mode:
            self._state.set_mode(target)

    def syncMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        target = self.nextMode()
        self.setIcon(overlay_icon(*self._iconFor(target)))
        self.setToolTip(
            self.tr("Switch to {}").format(self.labelFor(target))
            if target is not None and target is not mode
            else self.tr("{} is the only mode available here").format(
                self.labelFor(mode)
            )
        )
        action = self._actions.get(mode)
        if action is not None:
            action.setChecked(True)

    def syncAllowedModes(self, modes):
        self._rebuildMenu(tuple(modes))
        self.syncMode(self._state.mode)

    def _rebuildMenu(self, modes):
        menu = self.menu()
        menu.clear()
        self._actions = {}
        group = QActionGroup(menu)
        group.setExclusive(True)
        for mode in modes:
            action = QAction(self.labelFor(mode), menu)
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(
                lambda _checked=False, selected=mode:
                    self._state.set_mode(selected)
            )
            menu.addAction(action)
            self._actions[mode] = action

    def _iconFor(self, mode):
        if mode is MarkdownPresentationMode.READING:
            return self._READING_ICON
        if mode is MarkdownPresentationMode.SOURCE:
            return self._SOURCE_ICON
        return self._EDIT_ICON
