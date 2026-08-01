from PyQt5.QtCore import QSettings


class ProjectHistory:
    """Persist project discovery and welcome-screen preferences."""

    def __init__(self, settings=None):
        self._settings = settings if settings is not None else QSettings()

    def remember_last_project(self, project_file):
        self._settings.setValue("lastProject", project_file)

    def clear_last_project(self):
        self._settings.setValue("lastProject", "")

    def auto_load_values(self):
        enabled = self._settings.value(
            "autoLoad",
            defaultValue=False,
            type=bool,
        )
        if enabled and self._settings.contains("lastProject"):
            project_file = self._settings.value("lastProject")
        else:
            project_file = ""
        return bool(enabled), project_file or ""

    def set_auto_load(self, enabled):
        if isinstance(enabled, bool):
            self._settings.setValue("autoLoad", enabled)

    def last_accessed_directory(self):
        return self._settings.value(
            "lastAccessedDirectory",
            defaultValue=".",
            type=str,
        )

    def set_last_accessed_directory(self, directory):
        self._settings.setValue("lastAccessedDirectory", directory)

    def recent_files(self):
        if not self._settings.contains("recentFiles"):
            return ()
        files = self._settings.value("recentFiles")
        if isinstance(files, str):
            return (files,)
        return tuple(files or ())

    def remember_recent_file(self, project_file, limit=10):
        recent_files = list(self.recent_files())
        while project_file in recent_files:
            recent_files.remove(project_file)
        recent_files.insert(0, project_file)
        self._settings.setValue(
            "recentFiles",
            recent_files[:limit],
        )
