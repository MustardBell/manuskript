from manuskript import loadSave


class ProjectStorage:
    """Persistence boundary used by the project lifecycle."""

    def load(self, context):
        return loadSave.loadProject(context)

    def save(self, context, version=None):
        return loadSave.saveProject(context, version=version)

    def clear_cache(self):
        loadSave.clearSaveCache()
