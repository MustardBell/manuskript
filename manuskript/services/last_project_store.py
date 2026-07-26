from PyQt5.QtCore import QSettings


class LastProjectStore:
    """Persist the project path used by welcome-screen auto-load."""

    def __init__(self, settings=None):
        self._settings = settings if settings is not None else QSettings()

    def remember(self, project_file):
        self._settings.setValue("lastProject", project_file)

    def clear(self):
        self._settings.setValue("lastProject", "")
