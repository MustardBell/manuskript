from dataclasses import dataclass

from manuskript.ui.views.outline_context import OutlineViewContext


@dataclass(frozen=True)
class EditorContext:
    """Project-scoped dependencies used by the persistent main editor."""

    outline_model: object
    outline_tree: object
    outline_views: OutlineViewContext
