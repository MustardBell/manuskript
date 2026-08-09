import json
import logging
from copy import deepcopy

from PyQt5.QtWidgets import QToolTip, qApp

# Import default settings
from manuskript import settings as default_settings
from manuskript.settings_migrations import (
    SETTINGS_VERSION,
    VERSION_KEY,
    upgrade,
)
from manuskript.ui.tooltip_style import accessible_tooltip_palette

LOGGER = logging.getLogger(__name__)


class SettingsManager:
    _setting_names = (
        "viewSettings",
        "fullscreenSettings",
        "dict",
        "spellcheck",
        "corkSizeFactor",
        "folderView",
        "lastTab",
        "openIndexes",
        "progressChars",
        "countSpaces",
        "autoSave",
        "autoSaveDelay",
        "saveOnQuit",
        "autoSaveNoChanges",
        "autoSaveNoChangesDelay",
        "outlineViewColumns",
        "corkBackground",
        "indexCardStyle",
        "fullScreenTheme",
        "defaultTextType",
        "textEditor",
        "revisions",
        "frequencyAnalyzer",
        "viewMode",
        "saveToZip",
        "dontShowDeleteWarning",
        "tooltipStyle",
    )

    def _initialize_from_defaults(self):
        """Initialize active settings without sharing mutable default values."""
        for name in self._setting_names:
            setattr(self, name, deepcopy(getattr(default_settings, name)))

    def __init__(self):
        self._default_cursor_flash_time = None
        self._initialize_from_defaults()
        self.initDefaultValues()

    def configure_cursor_flash_time(self, default_value):
        """Inject a callable returning the platform's cursor flash interval."""
        if not callable(default_value):
            raise TypeError("default cursor flash time must be callable")
        self._default_cursor_flash_time = default_value

    def save(self, filename=None, protocol=None):
        """Save the current settings as JSON.

        ``filename`` and ``protocol`` are retained for load/save compatibility.
        """
        allSettings = {name: getattr(self, name) for name in self._setting_names}
        # Version is file metadata rather than a setting, so it is not in
        # _setting_names and is not exposed as an attribute.
        allSettings[VERSION_KEY] = SETTINGS_VERSION
        return json.dumps(json.loads(json.dumps(allSettings)), indent=4, sort_keys=True)

    def _load_basic_settings(self, allSettings):
        """Load settings that do not require compatibility handling."""
        self.viewSettings = allSettings.get("viewSettings", self.viewSettings)
        for cat, name, default in [("Tree", "iconSize", 24)]:
            if cat in self.viewSettings and name not in self.viewSettings[cat]:
                self.viewSettings[cat][name] = default

        self.fullscreenSettings = allSettings.get("fullscreenSettings", self.fullscreenSettings)
        self.dict = allSettings.get("dict", self.dict)
        self.spellcheck = allSettings.get("spellcheck", self.spellcheck)
        self.corkSizeFactor = allSettings.get("corkSizeFactor", self.corkSizeFactor)
        self.folderView = allSettings.get("folderView", self.folderView)
        self.lastTab = allSettings.get("lastTab", self.lastTab)
        self.openIndexes = allSettings.get("openIndexes", self.openIndexes)
        self.progressChars = allSettings.get("progressChars", self.progressChars)
        self.countSpaces = allSettings.get("countSpaces", self.countSpaces)
        self.autoSave = allSettings.get("autoSave", self.autoSave)
        self.autoSaveDelay = allSettings.get("autoSaveDelay", self.autoSaveDelay)
        self.saveOnQuit = allSettings.get("saveOnQuit", self.saveOnQuit)
        self.autoSaveNoChanges = allSettings.get("autoSaveNoChanges", self.autoSaveNoChanges)
        self.autoSaveNoChangesDelay = allSettings.get("autoSaveNoChangesDelay", self.autoSaveNoChangesDelay)
        self.outlineViewColumns = allSettings.get("outlineViewColumns", self.outlineViewColumns)
        self.corkBackground = allSettings.get("corkBackground", self.corkBackground)
        self.indexCardStyle = allSettings.get(
            "indexCardStyle", self.indexCardStyle
        )
        self.fullScreenTheme = allSettings.get("fullScreenTheme", self.fullScreenTheme)
        self.defaultTextType = allSettings.get("defaultTextType", self.defaultTextType)
        self.frequencyAnalyzer = allSettings.get("frequencyAnalyzer", self.frequencyAnalyzer)
        self.viewMode = allSettings.get("viewMode", self.viewMode)
        self.saveToZip = allSettings.get("saveToZip", self.saveToZip)
        self.dontShowDeleteWarning = allSettings.get(
            "dontShowDeleteWarning", self.dontShowDeleteWarning
        )

    def _load_text_editor_settings(self, allSettings):
        """Load text editor settings with backward-compatible defaults."""
        if "textEditor" in allSettings:
            self.textEditor = allSettings["textEditor"]
            added = {
                "textAlignment": 0,
                "cursorWidth": 1,
                "cursorNotBlinking": False,
                "maxWidth": 600,
                "marginsLR": 0,
                "marginsTB": 20,
                "backgroundTransparent": False,
                "alwaysCenter": False,
                "focusMode": False,
                "markdownDefaultMode": "formatted-source",
            }
            for k in added:
                if k not in self.textEditor:
                    self.textEditor[k] = added[k]

    def _load_revisions_settings(self, allSettings):
        """Load revisions settings and restore integer rule keys."""
        if "revisions" not in allSettings:
            return

        loaded = allSettings["revisions"]
        merged = deepcopy(default_settings.revisions)
        merged.update({
            key: value
            for key, value in loaded.items()
            if key not in ("rules", "git")
        })
        merged["git"].update(loaded.get("git") or {})

        loaded_rules = loaded.get("rules") or {}
        if loaded_rules:
            rules = {}
            for key, value in loaded_rules.items():
                if key == "null" or key is None:
                    rules[None] = value
                else:
                    rules[int(key)] = value
            merged["rules"] = rules

        self.revisions = merged

    def _load_tooltip_settings(self, allSettings):
        """Load tooltip settings with backward-compatible defaults."""
        if "tooltipStyle" in allSettings:
            self.tooltipStyle = allSettings["tooltipStyle"]
            if "useSystemDefaultsForTooltips" not in self.tooltipStyle:
                self.tooltipStyle["useSystemDefaultsForTooltips"] = True

    def load(self, string, fromString=False, protocol=None):
        """Load settings from a JSON string.

        ``fromString`` and ``protocol`` are retained for load/save compatibility.
        """
        if not string:
            LOGGER.error("Cannot load settings from empty string.")
            return

        allSettings = upgrade(json.loads(string))
        self._load_basic_settings(allSettings)
        self._load_text_editor_settings(allSettings)
        self._load_revisions_settings(allSettings)
        self._load_tooltip_settings(allSettings)
        self.apply_loaded_settings_effects()

    def initDefaultValues(self):
        """
        Initialize values that depend on the environment.
        """
        if not self.textEditor["background"]:
            from manuskript.ui import style as S
            self.textEditor["background"] = S.base
        if not self.textEditor["fontColor"]:
            from manuskript.ui import style as S
            self.textEditor["fontColor"] = S.text

    def apply_loaded_settings_effects(self):
        """
        Apply side-effects that interact with Qt's application state.
        """
        self.applyTooltipStyle()
        self.applyCursorFlashTime()

    def applyTooltipStyle(self):
        """
        Apply tooltip styling to the application.
        """
        if not self.tooltipStyle.get("useSystemDefaultsForTooltips", True):
            self._applyStyleSheet(
                "QToolTip {{ color: {}; background-color: {}; "
                "border: 1px solid {}; }}".format(
                    self.tooltipStyle["textColor"],
                    self.tooltipStyle["backgroundColor"],
                    self.tooltipStyle["borderColor"],
                )
            )
        else:
            self._applyStyleSheet("")  # Reset to default
            QToolTip.setPalette(
                accessible_tooltip_palette(qApp.palette())
            )

    @staticmethod
    def _applyStyleSheet(sheet):
        """Assign the application stylesheet only when it would change.

        Qt re-polishes every widget in the application when a stylesheet is
        assigned, and it does so whether or not the new sheet differs from
        the old one: 77 ms, measured, on a window with 62 editors in it.

        Opening a project applies settings twice -- the defaults, then the
        project's own -- so that was 155 ms per open spent arriving at the
        sheet already in place, and the first of the two was superseded by
        the second before anybody could see it.

        Asking Qt what it currently has rather than remembering what we last
        set: there is no second copy of the answer to fall out of step.
        """
        if qApp.styleSheet() != sheet:
            qApp.setStyleSheet(sheet)

    def applyCursorFlashTime(self):
        """
        Apply cursor flash time based on settings.
        """
        if self.textEditor.get("cursorNotBlinking", False):
            qApp.setCursorFlashTime(0)
        elif self._default_cursor_flash_time is not None:
            qApp.setCursorFlashTime(self._default_cursor_flash_time())

    def reset_to_defaults(self):
        """Reset active settings to independent copies of their defaults."""
        self._initialize_from_defaults()
        self.initDefaultValues()
        self.apply_loaded_settings_effects()
