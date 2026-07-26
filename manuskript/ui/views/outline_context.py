from dataclasses import dataclass
from typing import Callable, Optional

from manuskript.ui.views.outline_colors import OutlineColorResolver


@dataclass(frozen=True)
class OutlineViewContext:
    """Project dependencies shared by outline-style item views."""

    character_model: object
    label_model: object
    status_model: object
    color_resolver: OutlineColorResolver
    open_index: Callable
    open_indexes: Callable
    selection_changed: Optional[Callable] = None
    show_status: Optional[Callable] = None
