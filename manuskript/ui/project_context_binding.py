from manuskript.models.references import ReferenceModels, ReferenceService
from manuskript.ui.editors.editor_context import EditorContext
from manuskript.ui.reference_navigation import reference_navigation_for
from manuskript.ui.search_context import (
    SearchContext,
    SearchResultViewAdapter,
)
from manuskript.ui.views.MDEditCompleter import MDEditCompleter
from manuskript.ui.views.outline_colors import OutlineColorResolver
from manuskript.ui.views.outline_context import OutlineViewContext
from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.views.text_editor_context import (
    text_editor_context_for,
)


class ProjectContextBinding:
    """Install and release cross-feature contexts for one project."""

    def __init__(self, window):
        self.window = window
        self.reference_service = None
        self.text_editor_context = None

    def bind(self, connect):
        if self.reference_service is not None:
            raise RuntimeError(
                "Project contexts must be released before rebinding."
            )

        window = self.window
        self.reference_service = ReferenceService(
            ReferenceModels(
                outline=window.mdlOutline,
                characters=window.mdlCharacter,
                plots=window.mdlPlots,
                world=window.mdlWorld,
                statuses=window.mdlStatus,
                labels=window.mdlLabels,
            ),
            reference_navigation_for(window),
        )
        self.text_editor_context = text_editor_context_for(
            window,
            window.settingsManager,
        )
        for editor in window.findChildren(textEditView):
            editor.set_text_editor_context(
                self.text_editor_context
            )

        outline_views = OutlineViewContext(
            character_model=window.mdlCharacter,
            label_model=window.mdlLabels,
            status_model=window.mdlStatus,
            settings=window.settingsManager,
            color_resolver=OutlineColorResolver(
                window.mdlCharacter,
                window.mdlLabels,
            ),
            open_index=window.openIndex,
            open_indexes=window.openIndexes,
            selection_changed=window.redacMetadata.selectionChanged,
            show_status=window.statusPresenter.show,
        )
        editor_context = EditorContext(
            outline_model=window.mdlOutline,
            outline_tree=window.treeRedacOutline,
            outline_views=outline_views,
            text_editor=self.text_editor_context,
        )
        window.treeRedacOutline.set_outline_context(outline_views)
        window.treeOutlineOutline.set_outline_context(outline_views)
        window.mainEditor.set_context(editor_context)

        window.treeRedacOutline.setModel(window.mdlOutline)
        window.redacMetadata.setModels(
            window.mdlOutline,
            window.mdlCharacter,
            window.mdlLabels,
            window.mdlStatus,
        )
        window.outlineItemEditor.setModels(
            window.mdlOutline,
            window.mdlCharacter,
            window.mdlLabels,
            window.mdlStatus,
        )
        window.treeOutlineOutline.setModel(window.mdlOutline)
        window.storylineView.setModels(
            window.mdlOutline,
            window.mdlCharacter,
            window.mdlPlots,
            self.reference_service,
            connect=connect,
        )

        window.cheatSheet.setModels(
            window.mdlOutline,
            window.mdlCharacter,
            window.mdlPlots,
            window.mdlWorld,
            self.reference_service,
            connect=connect,
        )
        completion_data = lambda: window.cheatSheet.data
        for editor in window.findChildren(MDEditCompleter):
            editor.setReferenceService(
                self.reference_service,
                completion_data,
            )
        window.widget.setContext(
            SearchContext.from_models(
                outline=window.mdlOutline,
                characters=window.mdlCharacter,
                flat_data=window.mdlFlatData,
                world=window.mdlWorld,
                plots=window.mdlPlots,
                result_views=SearchResultViewAdapter(
                    window,
                    self.reference_service,
                ),
            )
        )

    def unbind(self):
        window = self.window
        window.treeRedacOutline.set_outline_context(None)
        window.treeOutlineOutline.set_outline_context(None)
        window.mainEditor.clear_context()
        for editor in window.findChildren(textEditView):
            editor.set_text_editor_context(None)
        for editor in window.findChildren(MDEditCompleter):
            editor.setReferenceService(None)
        window.widget.clearContext()
        window.cheatSheet.clearModels()
        window.storylineView.clearModels()
        self.text_editor_context = None
        self.reference_service = None
