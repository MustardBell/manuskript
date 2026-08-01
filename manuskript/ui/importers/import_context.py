from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ImportContext:
    """Project models and UI callbacks required by an import operation."""

    outline_model: object
    character_model: object
    label_model: object
    status_model: object
    settings: object
    current_outline_index: Callable
    show_status: Callable
