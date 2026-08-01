import logging

from manuskript.enums import Outline
from manuskript.functions import toInt


LOGGER = logging.getLogger(__name__)


class OutlineSearchContext:
    """Resolve outline reference columns without global application access."""

    def __init__(
        self,
        character_name=None,
        status_name=None,
        label_name=None,
    ):
        self._character_name = character_name
        self._status_name = status_name
        self._label_name = label_name

    @classmethod
    def from_models(cls, character_model, status_model, label_model):
        """Build lookup adapters for one project's related models."""

        def character_name(character_id):
            character = character_model.getCharacterByID(character_id)
            if character is None:
                LOGGER.error("Character POV not found: %s", character_id)
                return ""
            return character.name()

        def item_name(model, row):
            item = model.item(toInt(row), 0)
            return item.text() if item is not None else ""

        return cls(
            character_name=character_name,
            status_name=lambda row: item_name(status_model, row),
            label_name=lambda row: item_name(label_model, row),
        )

    def value_for(self, item, column):
        value = item.data(column)
        if column == Outline.POV and value and self._character_name:
            return self._character_name(value)
        if column == Outline.status and self._status_name:
            return self._status_name(value)
        if column == Outline.label and self._label_name:
            return self._label_name(value)
        return value
