import logging

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.ui.views.cards import BUILTIN_CARD_STYLES, IndexCardStyle


LOGGER = logging.getLogger(__name__)


class IndexCardStyleService(QObject):
    """Resolve built-in and plugin-contributed cork card styles."""

    stylesChanged = pyqtSignal()

    DEFAULT_ID = "manuskript.card.plain"

    def __init__(self, registry=None, report_error=None, parent=None):
        super().__init__(parent)
        # Cork has to draw with plugins disabled, so the registry is optional.
        self.registry = registry
        self._report_error = report_error or (
            lambda _message, _duration=5000, _importance=2: None
        )
        self._builtins = {
            style.id: style() for style in BUILTIN_CARD_STYLES
        }

    def refresh(self):
        self.stylesChanged.emit()

    def styles(self):
        """(id, name) for every available style, built-ins first."""
        listed = [
            (style.id, style.name)
            for style in self._builtins.values()
        ]
        listed.extend(sorted(
            (
                contribution.descriptor.id,
                contribution.descriptor.name,
            )
            for contribution in self._contributions()
        ))
        return tuple(listed)

    def resolve(self, style_id):
        """The style for an ID, falling back to the default.

        A project can name a style whose plugin is no longer installed. That
        must draw the default card rather than break the cork view.
        """
        builtin = self._builtins.get(style_id)
        if builtin is not None:
            return builtin

        for contribution in self._contributions():
            if contribution.descriptor.id != style_id:
                continue
            style = self._build(contribution)
            if style is not None:
                return style
            break
        else:
            if style_id:
                LOGGER.warning(
                    "Unknown index card style %r; using %s.",
                    style_id,
                    self.DEFAULT_ID,
                )
        return self._builtins[self.DEFAULT_ID]

    def _contributions(self):
        if self.registry is None:
            return ()
        return self.registry.index_card_styles

    def _build(self, contribution):
        try:
            style = contribution.style_factory()
        except Exception as error:
            self.report_error(contribution, error)
            return None
        if not isinstance(style, IndexCardStyle):
            self.report_error(
                contribution,
                TypeError(
                    "Index card style factories must return "
                    "IndexCardStyle instances."
                ),
            )
            return None
        # The descriptor is the published identity; keep them in step.
        style.id = contribution.descriptor.id
        style.name = contribution.descriptor.name
        return style

    def report_error(self, contribution, error):
        message = "Index card style {} failed: {}: {}".format(
            contribution.descriptor.name,
            type(error).__name__,
            error,
        )
        LOGGER.exception(message)
        self._report_error(message, 8000, 2)
