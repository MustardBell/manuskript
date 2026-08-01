import os
import re
from dataclasses import dataclass

from PyQt5.QtCore import QSettings

from manuskript.functions import allPaths, appPath, writablePath
from manuskript.theme_data import (
    getThemeName,
    loadThemeDatas,
)


@dataclass(frozen=True)
class ThemeDescriptor:
    path: str
    name: str
    editable: bool


class ThemeRepository:
    """Own theme discovery and persistence rules."""

    THEME_DIRECTORY = os.path.join("resources", "themes")

    def __init__(
        self,
        *,
        theme_directories=None,
        writable_directory=None,
        application_directory=None,
        settings_factory=None,
    ):
        self.theme_directories = tuple(
            theme_directories
            if theme_directories is not None
            else allPaths(self.THEME_DIRECTORY)
        )
        self.writable_directory = (
            writable_directory
            if writable_directory is not None
            else writablePath(self.THEME_DIRECTORY)
        )
        self.application_directory = os.path.abspath(
            application_directory
            if application_directory is not None
            else appPath(self.THEME_DIRECTORY)
        )
        self._settings_factory = (
            settings_factory or self._qt_settings
        )

    def list(self):
        themes = []
        for directory in self.theme_directories:
            try:
                filenames = sorted(os.listdir(directory))
            except OSError:
                continue
            for filename in filenames:
                if os.path.splitext(filename)[1] != ".theme":
                    continue
                path = os.path.join(directory, filename)
                themes.append(
                    ThemeDescriptor(
                        path=path,
                        name=getThemeName(path),
                        editable=self.is_editable(path),
                    )
                )
        return themes

    def create(self, filename_stem, display_name):
        filename_stem = self._safe_filename_stem(filename_stem)
        path = self._unique_path(filename_stem)
        settings = self._settings_factory(path)
        settings.setValue("Name", display_name)
        settings.sync()
        return path

    def load(self, path):
        return loadThemeDatas(path)

    def save(self, path, data):
        if not self.is_editable(path):
            raise PermissionError(
                "Built-in themes cannot be modified: {}".format(path)
            )
        settings = self._settings_factory(path)
        for key, value in data.items():
            settings.setValue(key, value)
        settings.sync()

    def remove(self, path):
        if not self.is_editable(path):
            raise PermissionError(
                "Built-in themes cannot be removed: {}".format(path)
            )
        os.remove(path)

    def is_editable(self, path):
        path = os.path.abspath(path)
        try:
            return os.path.commonpath(
                (self.application_directory, path)
            ) != self.application_directory
        except ValueError:
            return True

    def _unique_path(self, filename_stem):
        index = 0
        while True:
            suffix = "" if index == 0 else "_{}".format(index)
            path = os.path.join(
                self.writable_directory,
                "{}{}.theme".format(filename_stem, suffix),
            )
            if not os.path.exists(path):
                return path
            index += 1

    @staticmethod
    def _safe_filename_stem(filename_stem):
        safe = re.sub(r"[^\w.-]+", "_", filename_stem)
        safe = safe.strip("._")
        return safe or "newtheme"

    @staticmethod
    def _qt_settings(path):
        return QSettings(path, QSettings.IniFormat)
