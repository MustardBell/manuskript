"""Point the views that show references between items at the project.

The storyline, the cheat sheet, and the editors that complete a reference
as it is typed. Bound together because all three read through the one
reference service, which is handed in: it is made of models and belongs to
the project, not to any of these panels.
"""


class ReferencePanelBinding:
    """The storyline, the cheat sheet and the completing editors."""

    def __init__(self, views, models):
        self.views = views
        self.models = models

    def bind(self, connect, references):
        views = self.views
        models = self.models
        views.storyline.setModels(
            models.outline,
            models.characters,
            models.plots,
            references,
            connect=connect,
        )
        views.cheat_sheet.setModels(
            models.outline,
            models.characters,
            models.plots,
            models.world,
            references,
            connect=connect,
        )
        # Asked for when a completion is offered, not now: the cheat sheet
        # fills in as the project loads.
        completion_data = lambda: views.cheat_sheet.data
        for editor in views.completers():
            editor.setReferenceService(references, completion_data)

    def unbind(self):
        views = self.views
        for editor in views.completers():
            editor.setReferenceService(None)
        views.cheat_sheet.clearModels()
        views.storyline.clearModels()
