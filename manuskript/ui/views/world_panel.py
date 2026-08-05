"""The widgets and model the world panel is made of."""

from dataclasses import dataclass
from typing import Any, Tuple


class WorldModels:
    """The one model the world panel works with.

    Read from the project runtime whenever asked: the panel is built once
    and the model under it is replaced with every project.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    @property
    def world(self):
        return self._runtime.models.world


@dataclass(frozen=True)
class WorldPanelView:
    """One window's world-building panel."""

    #: The hierarchy of world items, which owns the selection.
    tree: Any
    #: The tab area holding the selected item's detail views.
    tabs: Any
    #: Opens the menu of data sets that can be filled in.
    data_set_button: Any
    #: Every field bound to the selected item's model index.
    fields: Tuple[Any, ...] = ()

    @classmethod
    def for_window(cls, window):
        """This window's world widgets, read off it once."""
        return cls(
            tree=window.treeWorld,
            tabs=window.tabWorld,
            data_set_button=window.btnWorldEmptyData,
            fields=(
                window.txtWorldName,
                window.txtWorldDescription,
                window.txtWorldPassion,
                window.txtWorldConflict,
            ),
        )
