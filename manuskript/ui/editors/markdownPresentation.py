from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal


class MarkdownPresentationMode(Enum):
    """How a Markdown document is presented without changing its source."""

    SOURCE = "source"
    FORMATTED_SOURCE = "formatted-source"
    LIVE_PREVIEW = "live-preview"
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
    """Shared, persisted presentation state for every Markdown editor."""

    modeChanged = pyqtSignal(object)

    DEFAULT_MODE = MarkdownPresentationMode.FORMATTED_SOURCE
    SETTINGS_KEY = "markdownMode"

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        configured_mode = settings.textEditor.get(
            self.SETTINGS_KEY,
            self.DEFAULT_MODE.value,
        )
        try:
            self._mode = MarkdownPresentationMode.from_value(
                configured_mode
            )
        except ValueError:
            self._mode = self.DEFAULT_MODE
        self._persist()

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if mode is self._mode:
            return

        self._mode = mode
        self._persist()
        self.modeChanged.emit(mode)

    def _persist(self):
        self._settings.textEditor[self.SETTINGS_KEY] = self._mode.value
