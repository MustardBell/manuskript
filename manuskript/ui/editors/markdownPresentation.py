from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.ui.connections import weak_callback


class MarkdownPresentationMode(Enum):
    """How a Markdown document is presented without changing its source."""

    SOURCE = "source"
    FORMATTED_SOURCE = "formatted-source"
    LIVE_PREVIEW = "live-preview"
    CLEAN_EDITING = "clean-editing"
    READING = "reading"

    @classmethod
    def from_value(cls, value):
        if isinstance(value, cls):
            return value

        normalized = str(value).strip().lower().replace("_", "-")
        for mode in cls:
            if mode.value == normalized:
                return mode

        raise ValueError(
            "Unknown Markdown presentation mode: {!r}".format(value)
        )

    @property
    def is_editable(self):
        return self is not self.READING

    @property
    def reveals_active_block(self):
        return self is self.LIVE_PREVIEW

    @property
    def renders_markdown(self):
        return self is not self.SOURCE


class MarkdownPresentationState(QObject):
    """Presentation state owned by one editor leaf."""

    modeChanged = pyqtSignal(object)
    allowedModesChanged = pyqtSignal(object)

    DEFAULT_MODE = MarkdownPresentationMode.FORMATTED_SOURCE

    def __init__(self, mode=None, parent=None):
        super().__init__(parent)
        try:
            self._mode = MarkdownPresentationMode.from_value(
                mode if mode is not None else self.DEFAULT_MODE
            )
        except ValueError:
            self._mode = self.DEFAULT_MODE
        self._allowed_modes = tuple(MarkdownPresentationMode)

    @property
    def mode(self):
        return self._mode

    @property
    def allowed_modes(self):
        return self._allowed_modes

    def set_mode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if mode not in self._allowed_modes:
            return
        if mode is self._mode:
            return

        self._mode = mode
        self.modeChanged.emit(mode)

    def set_allowed_modes(self, modes):
        """Settle the order of the modes a leaf offers.

        Two rules make an order out of whatever was asked for, so that
        whoever composed the list -- a page type, a markup profile, a plugin
        adding to what another already chose -- does not have to reconcile it
        themselves:

        A mode named more than once keeps its *last* place, because naming it
        again is how a later voice says where it should sit. So source, live,
        source asks for live then source.

        Source is always offered. It is the one mode a document can always be
        shown in, and losing it would leave prose with no plain way back. Not
        asking for it puts it first; asking for it puts it where asked.
        """

        modes = tuple(
            MarkdownPresentationMode.from_value(mode)
            for mode in modes
        )
        if not modes:
            raise ValueError(
                "At least one presentation mode must remain available."
            )
        seen = set()
        kept = []
        for mode in reversed(modes):
            if mode not in seen:
                seen.add(mode)
                kept.append(mode)
        modes = tuple(reversed(kept))
        if MarkdownPresentationMode.SOURCE not in modes:
            modes = (MarkdownPresentationMode.SOURCE,) + modes
        if modes == self._allowed_modes:
            return
        self._allowed_modes = modes
        self.allowedModesChanged.emit(modes)
        if self._mode not in modes:
            preferred = (
                MarkdownPresentationMode.FORMATTED_SOURCE
                if MarkdownPresentationMode.FORMATTED_SOURCE in modes
                else modes[0]
            )
            self._mode = preferred
            self.modeChanged.emit(preferred)


class MarkdownPresentationBinding:
    """Bind one control surface to whichever editor state is active.

    The editor footer and the main-window menu are two presentations of the
    same leaf-owned state.  This owns the observer transition once: detach
    the old leaf, announce and synchronize the new one, and never retain the
    widget or controller receiving those callbacks.
    """

    def __init__(
        self,
        *,
        set_enabled,
        state_changed,
        sync_mode,
        sync_allowed_modes,
    ):
        self._set_enabled = weak_callback(set_enabled)
        self._state_changed = weak_callback(state_changed)
        self._sync_mode = weak_callback(sync_mode)
        self._sync_allowed_modes = weak_callback(sync_allowed_modes)
        self.state = None

    def attach(self, state):
        if state is self.state:
            return
        previous = self.state
        if previous is not None:
            try:
                previous.modeChanged.disconnect(self._sync_mode)
                previous.allowedModesChanged.disconnect(
                    self._sync_allowed_modes
                )
            except (RuntimeError, TypeError):
                pass

        self.state = state
        self._set_enabled(state is not None)
        self._state_changed(state)
        if state is None:
            return

        state.modeChanged.connect(self._sync_mode)
        state.allowedModesChanged.connect(self._sync_allowed_modes)
        self._sync_allowed_modes(state.allowed_modes)
        self._sync_mode(state.mode)

    def set_mode(self, mode):
        if self.state is not None:
            self.state.set_mode(mode)

    def dispose(self):
        self.attach(None)
        self._set_enabled = None
        self._state_changed = None
        self._sync_mode = None
        self._sync_allowed_modes = None


class MarkdownPresentationDefaults:
    """Read and write the seed mode used by newly created editor leaves."""

    SETTINGS_KEY = "markdownDefaultMode"
    LEGACY_SETTINGS_KEY = "markdownMode"
    DEFAULT_MODE = MarkdownPresentationState.DEFAULT_MODE

    @classmethod
    def load(cls, settings):
        configured_mode = settings.textEditor.get(
            cls.SETTINGS_KEY,
            settings.textEditor.get(
                cls.LEGACY_SETTINGS_KEY,
                cls.DEFAULT_MODE.value,
            ),
        )
        try:
            mode = MarkdownPresentationMode.from_value(configured_mode)
        except ValueError:
            mode = cls.DEFAULT_MODE
        settings.textEditor[cls.SETTINGS_KEY] = mode.value
        return mode

    @classmethod
    def store(cls, settings, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        settings.textEditor[cls.SETTINGS_KEY] = mode.value
