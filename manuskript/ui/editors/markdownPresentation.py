from dataclasses import dataclass
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


def presentation_mode_key(value):
    """Return the stable identity used by editor state.

    Built-in modes keep their enum identity so existing editor policy remains
    type-safe.  A contributed mode is addressed by its globally unique string
    id.  Persisted built-in strings still normalize to the enum.
    """

    if isinstance(value, PresentationModeDefinition):
        return value.key
    if isinstance(value, MarkdownPresentationMode):
        return value
    try:
        return MarkdownPresentationMode.from_value(value)
    except ValueError:
        mode_id = str(value).strip()
        if not mode_id:
            raise ValueError("Presentation mode ids cannot be empty.")
        return mode_id


def presentation_mode_is_editable(value):
    """Whether the canonical source editor is active and editable."""

    key = presentation_mode_key(value)
    return (
        key.is_editable
        if isinstance(key, MarkdownPresentationMode)
        # A contributed widget owns its own editing contract. The canonical
        # source editor is hidden while it is active, so keeping that hidden
        # editor read-only prevents accidental edits through stale shortcuts.
        else False
    )


def presentation_mode_renders_markdown(value):
    """Whether core should render Markdown in its canonical source view."""

    key = presentation_mode_key(value)
    return (
        key.renders_markdown
        if isinstance(key, MarkdownPresentationMode)
        # Contributed views are separate widgets. Their rendering belongs to
        # their owner and must not alter a hidden source editor's highlighter.
        else False
    )


def presentation_mode_reveals_active_block(value):
    """Whether core's source view reveals markup only at the cursor."""

    key = presentation_mode_key(value)
    return (
        key.reveals_active_block
        if isinstance(key, MarkdownPresentationMode)
        else False
    )


def _source_view(context, _definition):
    return context.source_editor


def _reading_view(context, _definition):
    return context.reading_view()


def contributed_presentation_view(context, definition):
    """Realize a plugin declaration through the host-owned bridge."""

    return context.contributed_view(definition)


_CORE_LABELS = {
    MarkdownPresentationMode.SOURCE: "Source",
    MarkdownPresentationMode.FORMATTED_SOURCE: "Formatted Source",
    MarkdownPresentationMode.LIVE_PREVIEW: "Live Preview",
    MarkdownPresentationMode.CLEAN_EDITING: "Clean Editing",
    MarkdownPresentationMode.READING: "Reading",
}


@dataclass(frozen=True)
class PresentationModeDefinition:
    """One catalogue entry and the factory that realizes it in a leaf."""

    id: str
    label: str
    view_factory: object
    owner_id: str = "core"
    error_handler: object = None
    widget_factory: object = None

    def __post_init__(self):
        mode_id = str(self.id).strip()
        label = str(self.label).strip()
        if not mode_id or not label:
            raise ValueError("Presentation modes require an id and label.")
        if not callable(self.view_factory):
            raise TypeError("Presentation mode view factories must be callable.")
        if self.widget_factory is not None and not callable(
            self.widget_factory
        ):
            raise TypeError(
                "Contributed presentation widgets require a callable factory."
            )
        object.__setattr__(self, "id", mode_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "owner_id", str(self.owner_id or ""))

    @property
    def key(self):
        return presentation_mode_key(self.id)


def core_presentation_modes():
    """The catalogue entries Manuskript itself declares, in cycle order."""

    return tuple(
        PresentationModeDefinition(
            mode.value,
            _CORE_LABELS[mode],
            _reading_view
            if mode is MarkdownPresentationMode.READING else _source_view,
        )
        for mode in MarkdownPresentationMode
    )


def core_presentation_mode(value):
    key = presentation_mode_key(value)
    if not isinstance(key, MarkdownPresentationMode):
        return None
    return next(
        definition
        for definition in core_presentation_modes()
        if definition.key is key
    )


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
        definitions = core_presentation_modes()
        self._definitions = {
            definition.key: definition for definition in definitions
        }
        self._allowed_modes = tuple(
            definition.key for definition in definitions
        )

    @property
    def mode(self):
        return self._mode

    @property
    def allowed_modes(self):
        return self._allowed_modes

    def definition_for(self, mode):
        """The declaration behind a currently known mode, if any."""

        key = presentation_mode_key(mode)
        return self._definitions.get(key) or core_presentation_mode(key)

    def label_for(self, mode):
        definition = self.definition_for(mode)
        if definition is not None:
            return definition.label
        key = presentation_mode_key(mode)
        value = getattr(key, "value", key)
        return str(value).replace("-", " ").replace("_", " ").title()

    def set_mode(self, mode):
        mode = presentation_mode_key(mode)
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

        definitions = tuple(
            mode
            if isinstance(mode, PresentationModeDefinition)
            else core_presentation_mode(mode)
            for mode in modes
        )
        if not definitions or any(
            definition is None for definition in definitions
        ):
            raise ValueError(
                "Presentation modes must be nonempty catalogue entries."
            )
        seen = set()
        kept = []
        for definition in reversed(definitions):
            if definition.key not in seen:
                seen.add(definition.key)
                kept.append(definition)
        definitions = tuple(reversed(kept))
        modes = tuple(definition.key for definition in definitions)
        if MarkdownPresentationMode.SOURCE not in modes:
            source = core_presentation_mode(MarkdownPresentationMode.SOURCE)
            definitions = (source,) + definitions
            modes = (MarkdownPresentationMode.SOURCE,) + modes
        changed = (
            modes != self._allowed_modes
            or any(
                self._definitions.get(definition.key) != definition
                for definition in definitions
            )
        )
        if not changed:
            return
        self._definitions = {
            definition.key: definition for definition in definitions
        }
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
        mode = presentation_mode_key(mode)
        settings.textEditor[cls.SETTINGS_KEY] = mode.value
