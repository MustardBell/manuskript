"""Panel descriptions and their application-wide registry, Qt-free."""

from manuskript.panels.descriptor import (
    DOCK,
    PLACEMENTS,
    SPLITTER_SLOT,
    PanelDescriptor,
    SplitterSlot,
)
from manuskript.panels.registry import (
    PanelRegistry,
    PanelRegistryError,
)

__all__ = [
    "DOCK",
    "PLACEMENTS",
    "SPLITTER_SLOT",
    "PanelDescriptor",
    "PanelRegistry",
    "PanelRegistryError",
    "SplitterSlot",
]
