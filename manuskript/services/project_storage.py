from manuskript import loadSave
from manuskript.load_save.project_files import Version1ProjectFiles


class ProjectStorage:
    """Persistence boundary used by the project lifecycle."""

    def __init__(self, file_cache=None, file_access=None):
        self._file_cache = (
            file_cache if file_cache is not None else {}
        )
        self._file_access = file_access or Version1ProjectFiles()

    def load(self, context):
        return loadSave.loadProject(
            context,
            cache=self._file_cache,
            file_access=self._file_access,
        )

    def save(self, context, version=None):
        return loadSave.saveProject(
            context,
            version=version,
            cache=self._file_cache,
            file_access=self._file_access,
        )

    def clear_cache(self):
        self._file_cache.clear()
