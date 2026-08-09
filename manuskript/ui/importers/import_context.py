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


@dataclass(frozen=True)
class ImportContextProvider:
    """Resolve the live project models required by a new import dialog."""

    models: Callable[[], object]
    settings: object
    current_outline_index: Callable
    show_status: Callable

    def create(self):
        models = self.models()
        return ImportContext(
            outline_model=models.outline,
            character_model=models.characters,
            label_model=models.labels,
            status_model=models.statuses,
            settings=self.settings,
            current_outline_index=self.current_outline_index,
            show_status=self.show_status,
        )
