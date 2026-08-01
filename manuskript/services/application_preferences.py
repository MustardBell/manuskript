from PyQt5.QtCore import QSettings


class ApplicationPreferences:
    """Own application-scoped style, language, and font preferences."""

    STYLE_KEY = "applicationStyle"
    TRANSLATION_KEY = "applicationTranslation"
    FONT_SIZE_KEY = "appFontSize"

    def __init__(self, settings=None):
        self._settings = (
            settings if settings is not None else QSettings()
        )

    @property
    def style(self):
        return self._optional_value(self.STYLE_KEY)

    @style.setter
    def style(self, value):
        self._set_value(self.STYLE_KEY, value)

    @property
    def translation(self):
        return self._optional_value(self.TRANSLATION_KEY)

    @translation.setter
    def translation(self, value):
        self._set_value(self.TRANSLATION_KEY, value)

    @property
    def font_size(self):
        value = self._optional_value(self.FONT_SIZE_KEY)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @font_size.setter
    def font_size(self, value):
        self._set_value(self.FONT_SIZE_KEY, int(value))

    def _optional_value(self, key):
        if not self._settings.contains(key):
            return None
        return self._settings.value(key)

    def _set_value(self, key, value):
        self._settings.setValue(key, value)
        self._settings.sync()
