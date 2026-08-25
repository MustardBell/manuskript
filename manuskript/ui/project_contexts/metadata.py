"""Point the views that show one item's own facts at the project.

No release step, and that is the behaviour as it stands rather than an
omission dressed up: these panels are re-pointed at the next project's
models when it opens, and nothing asks them anything in between. Giving
them a clear step is a change to what closing a project does, not part of
splitting one binding into four.
"""

from manuskript.panels.core import OUTLINE


class MetadataBinding:
    """The metadata panel and the outline item editor."""

    def __init__(self, views, models):
        self.views = views
        self.models = models
        self.bound = False

    def bind(self):
        views = self.views
        models = self.models
        if views.panel is not None:
            views.panel.setModels(
                models.outline,
                models.characters,
                models.labels,
                models.statuses,
                page_types=views.page_types(),
            )
        self.bound = True

    def attach_surface(self, instance):
        if not self.bound or instance.id != OUTLINE:
            return
        models = self.models
        instance.widget.outlineItemEditor.setModels(
            models.outline,
            models.characters,
            models.labels,
            models.statuses,
        )

    def detach_surface(self, _instance):
        pass

    def unbind(self):
        self.bound = False
