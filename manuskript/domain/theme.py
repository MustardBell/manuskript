from enum import Enum, auto


class ThemeEditorState(Enum):
    BROWSING = auto()
    EDITING = auto()


class InvalidThemeEditorTransition(RuntimeError):
    pass


class ThemeEditorSession:
    """Own the short-lived state of one theme editing transaction."""

    def __init__(self):
        self.state = ThemeEditorState.BROWSING
        self.path = None
        self.data = None

    @property
    def is_editing(self):
        return self.state is ThemeEditorState.EDITING

    def start(self, path, data):
        if self.is_editing:
            raise InvalidThemeEditorTransition(
                "A theme is already being edited."
            )
        self.path = path
        self.data = dict(data)
        self.state = ThemeEditorState.EDITING

    def update(self, key, value):
        self._require_editing()
        self.data[key] = value

    def finish(self):
        self._require_editing()
        self._reset()

    def cancel(self):
        self._require_editing()
        self._reset()

    def _require_editing(self):
        if not self.is_editing:
            raise InvalidThemeEditorTransition(
                "No theme is being edited."
            )

    def _reset(self):
        self.state = ThemeEditorState.BROWSING
        self.path = None
        self.data = None
