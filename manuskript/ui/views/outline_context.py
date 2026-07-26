from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class OutlineViewContext:
    """Project dependencies shared by outline-style item views."""

    character_model: object
    label_model: object
    status_model: object
    open_index: Callable
    open_indexes: Callable
    selection_changed: Optional[Callable] = None
