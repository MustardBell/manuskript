from manuskript import loadSave


class ProjectStorage:
    """Persistence boundary used by the project lifecycle."""

    def load(self, project, context):
        return loadSave.loadProject(project, window=context)

    def save(self, context, version=None):
        return loadSave.saveProject(version=version, window=context)

    def clear_cache(self):
        loadSave.clearSaveCache()
