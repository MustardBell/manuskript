"""Project lifecycle for the canonical entity workspace."""


class ProjectFeatureBinding:
    """Bind one entity workspace after project models have been loaded."""

    def __init__(self, entity_workspace):
        self.entityWorkspace = entity_workspace
        self.bound = False

    def bind(self, connect):
        if self.bound:
            raise RuntimeError(
                "Project features must be released before rebinding."
            )
        self.entityWorkspace.bind(connect)
        self.bound = True

    def unbind(self):
        if not self.bound:
            return
        self.entityWorkspace.unbind()
        self.bound = False

    def dispose(self):
        self.unbind()
        self.entityWorkspace.dispose()
        self.entityWorkspace = None
