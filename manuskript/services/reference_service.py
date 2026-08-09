"""Application service composing reference resolution, presentation, and navigation."""

from manuskript.models.references import (
    ID,
    ReferenceModels,
    ReferenceNavigation,
    findReferencesTo,
    open as open_reference,
    shortInfos,
    title,
    type as reference_type,
)


class ReferenceService:
    """One project's reference operations with explicit external dependencies."""

    def __init__(
        self,
        models: ReferenceModels,
        navigation: ReferenceNavigation,
        presentation,
    ):
        self.models = models
        self.navigation = navigation
        self.presentation = presentation

    def infos(self, ref):
        return self.presentation.infos(ref)

    def short_infos(self, ref):
        return shortInfos(ref, self.models)

    def title(self, ref):
        return title(ref, self.models)

    def reference_type(self, ref):
        return reference_type(ref, self.models)

    def reference_id(self, ref):
        return ID(ref, self.models)

    def tooltip(self, ref):
        return self.presentation.tooltip(ref)

    def to_link(self, ref):
        return self.presentation.to_link(ref)

    def linkify_all(self, text):
        return self.presentation.linkify_all(text)

    def find_references_to(self, ref, parent=None, recursive=True):
        return findReferencesTo(
            ref,
            self.models,
            parent=parent,
            recursive=recursive,
        )

    def list_references(self, ref, title=None):
        return self.presentation.list_references(ref, title=title)

    def basic_format(self, text):
        return self.presentation.basic_format(text)

    def open(self, ref):
        return open_reference(ref, self.navigation)
