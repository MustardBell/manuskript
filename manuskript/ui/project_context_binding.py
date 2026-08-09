"""Bind one project's cross-feature contexts, four areas at a time.

This class used to do all of it: build the reference service, install the
outline and editor contexts, point the metadata panel, the item editor, the
storyline, the cheat sheet, the completers and search at the models, and
release the lot. Every line could see every view, so the only thing keeping
search away from the metadata panel was that nobody had written the line.

What is left here is what genuinely spans the areas: the two objects more
than one of them needs, and the order they are bound in. Each area's own
work lives in :mod:`manuskript.ui.project_contexts`, and each of those
bindings is handed only its own views.
"""

from manuskript.models.references import ReferenceModels
from manuskript.services.reference_service import ReferenceService
from manuskript.ui.project_contexts import (
    EditorBinding,
    MetadataBinding,
    ReferencePanelBinding,
    SearchBinding,
)
from manuskript.ui.reference_presentation import ReferenceHtmlPresenter


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
        self.editors = EditorBinding(views.editors, views.models)
        self.metadata = MetadataBinding(views.metadata, views.models)
        self.reference_panels = ReferencePanelBinding(
            views.reference_panels,
            views.models,
        )
        self.search = SearchBinding(views.search, views.models)

    def bind(self, connect):
        if self.reference_service is not None:
            raise RuntimeError(
                "Project contexts must be released before rebinding."
            )

        # The reference service before any area: two of them resolve
        # references through it, and it is made of models rather than of
        # any window's widgets.
        reference_models = ReferenceModels.for_project(self.views.models)
        self.reference_service = ReferenceService(
            reference_models,
            self.views.navigation,
            ReferenceHtmlPresenter(reference_models),
        )
        # Editors before the rest, as before: a widget taking its models
        # can emit, and what it emits reaches whatever is bound already.
        self.text_editor_context = self.editors.bind()
        self.metadata.bind()
        self.reference_panels.bind(connect, self.reference_service)
        self.search.bind(self.reference_service)

    def unbind(self):
        """Release each area in turn, editors first.

        One area at a time rather than the old interleaving, which cleared
        the completers, then search, then the panels the completers read
        from. The widgets are disjoint, so the sequence within that was
        never load-bearing; being able to say what a release consists of
        is.
        """
        self.editors.unbind()
        self.reference_panels.unbind()
        self.search.unbind()
        self.text_editor_context = None
        self.reference_service = None
