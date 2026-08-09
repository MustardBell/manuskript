"""Point this window's editing views at the project, and let them go.

The outline trees, the document area and every model-backed text editor.
The text editor context is built here because this is where the editors
are, and handed back for the coordinator to share with anything else that
needs it.
"""

from manuskript.ui.editors.editor_context import EditorContext
from manuskript.ui.views.outline_colors import OutlineColorResolver
from manuskript.ui.views.outline_context import OutlineViewContext


class EditorBinding:
    """Where documents are edited, bound to the project's models."""

    def __init__(self, views, models):
        self.views = views
        self.models = models
        self.text_editor_context = None

    def bind(self):
        """Install the contexts, and answer with the text editor context.

        Editors first, then the trees and the document area: the same
        order the one large binding used, kept because a widget taking its
        models can emit, and what it emits reaches whatever is already
        bound.
        """
        views = self.views
        models = self.models
        self.text_editor_context = views.text_editor_context()
        for editor in views.text_editors():
            editor.set_text_editor_context(self.text_editor_context)

        outline_views = OutlineViewContext(
            character_model=models.characters,
            label_model=models.labels,
            status_model=models.statuses,
            settings=views.settings,
            color_resolver=OutlineColorResolver(
                models.characters,
                models.labels,
            ),
            card_styles=views.card_styles,
            undo_stack=views.undo_stack,
            open_index=views.open_index,
            open_indexes=views.open_indexes,
            selection_changed=views.selection_changed,
            show_status=views.show_status,
        )
        editor_context = EditorContext(
            outline_model=models.outline,
            outline_tree=views.outline_trees[0],
            outline_views=outline_views,
            text_editor=self.text_editor_context,
        )
        for tree in views.outline_trees:
            tree.bind_project_model(models.outline, outline_views)
        views.document_area.set_context(editor_context)
        return self.text_editor_context

    def unbind(self):
        views = self.views
        for tree in views.outline_trees:
            tree.unbind_project_model()
        views.document_area.clear_context()
        for editor in views.text_editors():
            editor.set_text_editor_context(None)
        self.text_editor_context = None
