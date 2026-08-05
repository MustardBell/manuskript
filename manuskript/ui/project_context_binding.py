from manuskript.models.references import ReferenceModels, ReferenceService
from manuskript.ui.editors.editor_context import EditorContext
from manuskript.ui.search_context import SearchContext
from manuskript.ui.views.outline_colors import OutlineColorResolver
from manuskript.ui.views.outline_context import OutlineViewContext


class ProjectContextBinding:
    """Install and release cross-feature contexts for one project.

    Takes the views it binds rather than a window to find them in. With
    one window "the outline tree" and "the editor" were unambiguous; with
    two, every such phrase is a question, and the answers belong to
    whoever assembled the view set.
    """

    def __init__(self, views):
        self.views = views
        self.reference_service = None
        self.text_editor_context = None

    def bind(self, connect):
        if self.reference_service is not None:
            raise RuntimeError(
                "Project contexts must be released before rebinding."
            )

        views = self.views
        models = views.models
        self.reference_service = ReferenceService(
            ReferenceModels(
                outline=models.outline,
                characters=models.characters,
                plots=models.plots,
                world=models.world,
                statuses=models.statuses,
                labels=models.labels,
            ),
            views.navigation,
        )
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

        views.metadata_panel.setModels(
            models.outline,
            models.characters,
            models.labels,
            models.statuses,
            page_types=views.page_types(),
        )
        views.item_editor.setModels(
            models.outline,
            models.characters,
            models.labels,
            models.statuses,
        )
        views.storyline.setModels(
            models.outline,
            models.characters,
            models.plots,
            self.reference_service,
            connect=connect,
        )

        views.cheat_sheet.setModels(
            models.outline,
            models.characters,
            models.plots,
            models.world,
            self.reference_service,
            connect=connect,
        )
        completion_data = lambda: views.cheat_sheet.data
        for editor in views.completers():
            editor.setReferenceService(
                self.reference_service,
                completion_data,
            )
        views.search_view.setContext(
            SearchContext.from_models(
                outline=models.outline,
                characters=models.characters,
                flat_data=models.flat_data,
                world=models.world,
                plots=models.plots,
                result_views=views.result_views(
                    self.reference_service
                ),
            )
        )

    def unbind(self):
        views = self.views
        for tree in views.outline_trees:
            tree.unbind_project_model()
        views.document_area.clear_context()
        for editor in views.text_editors():
            editor.set_text_editor_context(None)
        for editor in views.completers():
            editor.setReferenceService(None)
        views.search_view.clearContext()
        views.cheat_sheet.clearModels()
        views.storyline.clearModels()
        self.text_editor_context = None
        self.reference_service = None
