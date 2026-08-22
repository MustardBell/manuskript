"""Point this window's editing views at the project, and let them go.

The outline trees, the document area and every model-backed text editor.
The text editor context is built here because this is where the editors
are, and handed back for the coordinator to share with anything else that
needs it.
"""

from manuskript.ui.editors.editor_context import EditorContext
from manuskript.panels.core import EDITOR, OUTLINE
from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.views.outline_colors import OutlineColorResolver
from manuskript.ui.views.outline_context import OutlineViewContext


class EditorBinding:
    """Where documents are edited, bound to the project's models."""

    def __init__(self, views, models):
        self.views = views
        self.models = models
        self.text_editor_context = None
        self.outline_views = None
        self._surfaces = {}

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
        self.outline_views = OutlineViewContext(
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
        views.project_tree.bind_project_model(
            models.outline, self.outline_views,
        )
        return self.text_editor_context

    def attach_surface(self, instance):
        if self.text_editor_context is None:
            return
        if instance.id == OUTLINE:
            instance.widget.treeOutlineOutline.bind_project_model(
                self.models.outline, self.outline_views,
            )
        elif instance.id == EDITOR:
            panel = instance.widget
            for editor in panel.findChildren(textEditView):
                editor.set_text_editor_context(self.text_editor_context)
            panel.editor.set_context(EditorContext(
                outline_model=self.models.outline,
                outline_tree=self.views.project_tree,
                outline_views=self.outline_views,
                text_editor=self.text_editor_context,
            ))
        else:
            return
        self._surfaces[instance.id] = instance

    def detach_surface(self, instance):
        if self._surfaces.pop(instance.id, None) is None:
            return
        if instance.id == OUTLINE:
            instance.widget.treeOutlineOutline.unbind_project_model()
        elif instance.id == EDITOR:
            panel = instance.widget
            panel.editor.clear_context()
            for editor in panel.findChildren(textEditView):
                editor.set_text_editor_context(None)

    def unbind(self):
        for instance in reversed(tuple(self._surfaces.values())):
            self.detach_surface(instance)
        self.views.project_tree.unbind_project_model()
        self.text_editor_context = None
        self.outline_views = None
