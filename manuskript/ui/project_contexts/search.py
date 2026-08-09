"""Point search at the project, and let it go.

Search reads five of the project's models and shows its results through
this window's own result views. It is given the reference service because a
result describes what it found; it does not build one.
"""

from manuskript.ui.search_context import SearchContext


class SearchBinding:
    """Where the project is searched from."""

    def __init__(self, views, models):
        self.views = views
        self.models = models

    def bind(self, references):
        views = self.views
        models = self.models
        views.view.setContext(
            SearchContext.from_models(
                outline=models.outline,
                characters=models.characters,
                flat_data=models.flat_data,
                world=models.world,
                plots=models.plots,
                result_views=views.result_views(references),
            )
        )

    def unbind(self):
        self.views.view.clearContext()
