"""Panel descriptions and their application-wide registry, Qt-free."""

from manuskript.panels.context import PanelContext
from manuskript.panels.descriptor import (
    APPLICATION,
    DOCK,
    MULTIPLICITIES,
    PER_WINDOW,
    PLACEMENTS,
    PROJECT,
    NavigatorEntry,
    SCOPES,
    SINGLETON,
    SPLITTER_SLOT,
    WorkspaceItemDescriptor,
    group_of,
    ToolPanelDescriptor,
    WorkspaceSurfaceDescriptor,
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
    "NavigatorEntry",
    "SCOPES",
    "SINGLETON",
    "SPLITTER_SLOT",
    "PanelContext",
    "WorkspaceItemDescriptor",
    "group_of",
    "ToolPanelDescriptor",
    "WorkspaceSurfaceDescriptor",
    "PanelState",
    "PanelRegistry",
    "PanelRegistryError",
    "SplitterSlot",
]
