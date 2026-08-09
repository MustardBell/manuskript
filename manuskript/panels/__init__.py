"""Panel descriptions and their application-wide registry, Qt-free."""

from manuskript.panels.context import PanelContext
from manuskript.panels.descriptor import (
    APPLICATION,
    DOCK,
    MULTIPLICITIES,
    PER_WINDOW,
    PLACEMENTS,
    PROJECT,
    SCOPES,
    SINGLETON,
    SPLITTER_SLOT,
    PanelDescriptor,
    PanelState,
    SplitterSlot,
)
from manuskript.panels.registry import (
    PanelRegistry,
    PanelRegistryError,
)

__all__ = [
    "APPLICATION",
    "DOCK",
    "MULTIPLICITIES",
    "PER_WINDOW",
    "PLACEMENTS",
    "PROJECT",
    "SCOPES",
    "SINGLETON",
    "SPLITTER_SLOT",
    "PanelContext",
    "PanelDescriptor",
    "PanelState",
    "PanelRegistry",
    "PanelRegistryError",
    "SplitterSlot",
]
