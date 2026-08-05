"""The widgets and models the character panel is made of.

Named so that the controller is handed its panel rather than a window to
find one in. The list of fields is long because the panel has that many
parts; the difference is that it is a list, in one place, instead of
reaching for whatever a window happens to expose.
"""

from dataclasses import dataclass
from typing import Any, Tuple


class CharacterModels:
    """The two models the character panel works with.

    Read from the project runtime whenever asked, because a controller
    outlives any one project: the panel is built once and the models are
    replaced under it every time a project opens.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    @property
    def characters(self):
        return self._runtime.models.characters

    @property
    def outline(self):
        return self._runtime.models.outline


@dataclass(frozen=True)
class CharacterPanelView:
    """One window's character panel."""

    #: The list of characters, which owns the selection.
    characters: Any
    #: The tab area the panel's detail views live in, and which the bulk
    #: editor temporarily replaces.
    tabs: Any
    #: The table of a character's extra information.
    info: Any
    color_button: Any
    pov_checkbox: Any
    importance_slider: Any
    #: Every field bound to the selected character's model index.
    fields: Tuple[Any, ...] = ()

    @classmethod
    def for_window(cls, window):
        """This window's character widgets, read off it once."""
        return cls(
            characters=window.lstCharacters,
            tabs=window.tabPersos,
            info=window.tblPersoInfos,
            color_button=window.btnPersoColor,
            pov_checkbox=window.chkPersoPOV,
            importance_slider=window.sldPersoImportance,
            fields=(
                window.txtPersoName,
                window.sldPersoImportance,
                window.txtPersoMotivation,
                window.txtPersoGoal,
                window.txtPersoConflict,
                window.txtPersoEpiphany,
                window.txtPersoSummarySentence,
                window.txtPersoSummaryPara,
                window.txtPersoSummaryFull,
                window.txtPersoNotes,
            ),
        )
