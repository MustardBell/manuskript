import json
import logging
from copy import deepcopy

from PyQt5.QtWidgets import qApp

# Import default settings
from manuskript import settings as default_settings

LOGGER = logging.getLogger(__name__)


class SettingsManager:
    _instance = None
    _initialized = False
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
        "corkStyle",
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

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
        return cls._instance

    def _initialize_from_defaults(self):
        """Initialize active settings without sharing mutable default values."""
        for name in self._setting_names:
            setattr(self, name, deepcopy(getattr(default_settings, name)))

    def __init__(self):
        if SettingsManager._initialized:
            return
        self._initialize_from_defaults()
        self.initDefaultValues()
        SettingsManager._initialized = True

    def save(self, filename=None, protocol=None):
        """Save the current settings as JSON.

        ``filename`` and ``protocol`` are retained for load/save compatibility.
        """
        allSettings = {name: getattr(self, name) for name in self._setting_names}
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
        self.corkStyle = allSettings.get("corkStyle", self.corkStyle)
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
            }
            for k in added:
                if k not in self.textEditor:
                    self.textEditor[k] = added[k]

    def _load_revisions_settings(self, allSettings):
        """Load revisions settings and restore integer rule keys."""
        if "revisions" in allSettings:
            self.revisions = allSettings["revisions"]
            r = {}
            for i in self.revisions["rules"]:
                if i == "null":
                    r[None] = self.revisions["rules"]["null"]
                elif i is None:
                    r[None] = self.revisions["rules"][None]
                else:
                    r[int(i)] = self.revisions["rules"][i]
            self.revisions["rules"] = r

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

        allSettings = json.loads(string)
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
            qApp.setStyleSheet(
                "QToolTip {{ color: {}; background-color: {}; "
                "border: 1px solid {}; }}".format(
                    self.tooltipStyle["textColor"],
                    self.tooltipStyle["backgroundColor"],
                    self.tooltipStyle["borderColor"],
                )
            )
        else:
            qApp.setStyleSheet("")  # Reset to default

    def applyCursorFlashTime(self):
        """
        Apply cursor flash time based on settings.
        """
        if self.textEditor.get("cursorNotBlinking", False):
            qApp.setCursorFlashTime(0)
        else:
            from manuskript.functions import mainWindow
            if mainWindow():
                qApp.setCursorFlashTime(mainWindow()._defaultCursorFlashTime)

    def reset_to_defaults(self):
        """Reset active settings to independent copies of their defaults."""
        self._initialize_from_defaults()
        self.initDefaultValues()
        self.apply_loaded_settings_effects()
