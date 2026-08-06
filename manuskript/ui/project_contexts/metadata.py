"""Point the views that show one item's own facts at the project.

No release step, and that is the behaviour as it stands rather than an
omission dressed up: these panels are re-pointed at the next project's
models when it opens, and nothing asks them anything in between. Giving
them a clear step is a change to what closing a project does, not part of
splitting one binding into four.
"""


class MetadataBinding:
    """The metadata panel and the outline item editor."""

    def __init__(self, views, models):
        self.views = views
        self.models = models

    def bind(self):
        views = self.views
        models = self.models
        views.panel.setModels(
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
