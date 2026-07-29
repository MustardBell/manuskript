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
    """Presentation state owned by one editor leaf."""

    modeChanged = pyqtSignal(object)

    DEFAULT_MODE = MarkdownPresentationMode.FORMATTED_SOURCE

    def __init__(self, mode=None, parent=None):
        super().__init__(parent)
        try:
            self._mode = MarkdownPresentationMode.from_value(
                mode if mode is not None else self.DEFAULT_MODE
            )
        except ValueError:
            self._mode = self.DEFAULT_MODE

    @property
    def mode(self):
        return self._mode

    def set_mode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if mode is self._mode:
            return

        self._mode = mode
        self.modeChanged.emit(mode)


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
