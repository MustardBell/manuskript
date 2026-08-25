"""Point the views that show references between items at the project.

The storyline, the cheat sheet, and the editors that complete a reference
as it is typed. Bound together because all three read through the one
reference service, which is handed in: it is made of models and belongs to
the project, not to any of these panels.
"""

from manuskript.panels.core import EDITOR
from manuskript.ui.views.MDEditCompleter import MDEditCompleter


class ReferencePanelBinding:
    """The storyline, the cheat sheet and the completing editors."""

    def __init__(self, views, models):
        self.views = views
        self.models = models
        self.references = None
        self._completers = {}

    def bind(self, connect, references):
        views = self.views
        models = self.models
        if views.storyline is not None:
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
        self.references = references

    def attach_surface(self, instance):
        if self.references is None or instance.id != EDITOR:
            return
        completers = tuple(instance.widget.findChildren(MDEditCompleter))
        completion_data = lambda: self.views.cheat_sheet.data
        for editor in completers:
            editor.setReferenceService(self.references, completion_data)
        self._completers[instance.id] = completers

    def detach_surface(self, instance):
        for editor in self._completers.pop(instance.id, ()):
            editor.setReferenceService(None)

    def unbind(self):
        views = self.views
        for instance_id in tuple(self._completers):
            for editor in self._completers.pop(instance_id):
                editor.setReferenceService(None)
        views.cheat_sheet.clearModels()
        if views.storyline is not None:
            views.storyline.clearModels()
        self.references = None
