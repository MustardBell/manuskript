from manuskript import loadSave


class ProjectStorage:
    """Persistence boundary used by the project lifecycle."""

    def __init__(self, file_cache=None):
        self._file_cache = (
            file_cache if file_cache is not None else {}
        )

    def load(self, context):
        return loadSave.loadProject(
            context,
            cache=self._file_cache,
        )

    def save(self, context, version=None):
        return loadSave.saveProject(
            context,
            version=version,
            cache=self._file_cache,
        )

    def clear_cache(self):
        self._file_cache.clear()
