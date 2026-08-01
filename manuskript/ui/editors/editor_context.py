from dataclasses import dataclass
from typing import Optional

from manuskript.ui.views.outline_context import OutlineViewContext
from manuskript.ui.views.text_editor_context import TextEditorContext


@dataclass(frozen=True)
class EditorContext:
    """Project-scoped dependencies used by the persistent main editor."""

    outline_model: object
    outline_tree: object
    outline_views: OutlineViewContext
    text_editor: Optional[TextEditorContext] = None
