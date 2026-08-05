"""Index card styles for the cork board."""

from manuskript.ui.views.cards.base import (
    CardContext,
    CardLayout,
    IndexCardStyle,
)
from manuskript.ui.views.cards.plain import PlainCardStyle
from manuskript.ui.views.cards.ruled import RuledCardStyle

BUILTIN_CARD_STYLES = (PlainCardStyle, RuledCardStyle)

__all__ = [
    "BUILTIN_CARD_STYLES",
    "CardContext",
    "CardLayout",
    "IndexCardStyle",
    "PlainCardStyle",
    "RuledCardStyle",
]
