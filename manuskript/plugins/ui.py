"""Published base classes that plugins subclass to draw their own widgets.

Separate from :mod:`manuskript.plugins` on purpose. That module holds the
contracts a plugin *constructs* — plain dataclasses that carry no Qt — so it
stays importable by anything, including tooling that never starts a GUI.
The classes here are ones a plugin *inherits from*, and they necessarily
bring Qt with them.

Importing this module does not require a running QApplication.
"""

from manuskript.ui.views.cards.base import (
    CardContext,
    CardLayout,
    IndexCardStyle,
)

__all__ = [
    "CardContext",
    "CardLayout",
    "IndexCardStyle",
]
