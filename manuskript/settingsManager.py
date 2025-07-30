import json
import logging
from PyQt5.QtWidgets import qApp

# Import default settings
from manuskript import settings as default_settings

LOGGER = logging.getLogger(__name__)

class SettingsManager:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if SettingsManager._initialized:
            return
        # Initialize settings with default values from the settings module
        self.viewSettings = default_settings.viewSettings.copy()
        self.fullscreenSettings = default_settings.fullscreenSettings.copy()
        self.dict = default_settings.dict
        self.spellcheck = default_settings.spellcheck
        self.corkSizeFactor = default_settings.corkSizeFactor
        self.folderView = default_settings.folderView
        self.lastTab = default_settings.lastTab
        self.openIndexes = default_settings.openIndexes.copy()
        self.progressChars = default_settings.progressChars
        self.countSpaces = default_settings.countSpaces
        self.autoSave = default_settings.autoSave
        self.autoSaveDelay = default_settings.autoSaveDelay
        self.saveOnQuit = default_settings.saveOnQuit
        self.autoSaveNoChanges = default_settings.autoSaveNoChanges
        self.autoSaveNoChangesDelay = default_settings.autoSaveNoChangesDelay
        self.outlineViewColumns = default_settings.outlineViewColumns.copy()
        self.corkBackground = default_settings.corkBackground.copy()
        self.corkStyle = default_settings.corkStyle
        self.fullScreenTheme = default_settings.fullScreenTheme
        self.defaultTextType = default_settings.defaultTextType
        self.textEditor = default_settings.textEditor.copy()
        self.revisions = default_settings.revisions.copy()
        self.frequencyAnalyzer = default_settings.frequencyAnalyzer.copy()
        self.viewMode = default_settings.viewMode
        self.saveToZip = default_settings.saveToZip
        self.dontShowDeleteWarning = default_settings.dontShowDeleteWarning
        self.tooltipStyle = default_settings.tooltipStyle.copy()
        
        self.initDefaultValues()
        SettingsManager._initialized = True

    def save(self, filename=None, protocol=None):
        """Saves the current settings into a JSON string.
        
        Note: filename and protocol parameters seem to be unused but are kept for compatibility."""
        allSettings = {
            "viewSettings": self.viewSettings,
            "fullscreenSettings": self.fullscreenSettings,
            "dict": self.dict,
            "spellcheck": self.spellcheck,
            "corkSizeFactor": self.corkSizeFactor,
            "folderView": self.folderView,
            "lastTab": self.lastTab,
            "openIndexes": self.openIndexes,
            "progressChars": self.progressChars,
            "countSpaces": self.countSpaces,
            "autoSave": self.autoSave,
            "autoSaveDelay": self.autoSaveDelay,
            "saveOnQuit": self.saveOnQuit,
            "autoSaveNoChanges": self.autoSaveNoChanges,
            "autoSaveNoChangesDelay": self.autoSaveNoChangesDelay,
            "outlineViewColumns": self.outlineViewColumns,
            "corkBackground": self.corkBackground,
            "corkStyle": self.corkStyle,
            "fullScreenTheme": self.fullScreenTheme,
            "defaultTextType": self.defaultTextType,
            "textEditor": self.textEditor,
            "revisions": self.revisions,
            "frequencyAnalyzer": self.frequencyAnalyzer,
            "viewMode": self.viewMode,
            "saveToZip": self.saveToZip,
            "dontShowDeleteWarning": self.dontShowDeleteWarning,
            "tooltipStyle": self.tooltipStyle,
        }
        return json.dumps(json.loads(json.dumps(allSettings)), indent=4, sort_keys=True)

    def load(self, string, fromString=False, protocol=None):
        """Loads settings from a JSON string.
        
        Note: fromString and protocol parameters seem to be unused but are kept for compatibility."""
        if not string:
            LOGGER.error("Cannot load settings from empty string.")
            return

        allSettings = json.loads(string)

        # Use dict.get(key, default_value) for safer loading
        self.viewSettings = allSettings.get("viewSettings", self.viewSettings)
        # Ensure backward compatibility for missing keys
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
        
        # Special handling for textEditor with backward compatibility
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
        
        # Special handling for revisions with key conversion
        if "revisions" in allSettings:
            self.revisions = allSettings["revisions"]
            r = {}
            for i in self.revisions["rules"]:
                if i == "null":
                    r[None] = self.revisions["rules"]["null"]
                elif i == None:
                    r[None] = self.revisions["rules"][None]
                else:
                    r[int(i)] = self.revisions["rules"][i]
            self.revisions["rules"] = r

        self.frequencyAnalyzer = allSettings.get("frequencyAnalyzer", self.frequencyAnalyzer)
        self.viewMode = allSettings.get("viewMode", self.viewMode)
        self.saveToZip = allSettings.get("saveToZip", self.saveToZip)
        self.dontShowDeleteWarning = allSettings.get("dontShowDeleteWarning", self.dontShowDeleteWarning)
        
        # Special handling for tooltipStyle with backward compatibility
        if "tooltipStyle" in allSettings:
            self.tooltipStyle = allSettings["tooltipStyle"]
            if "useSystemDefaultsForTooltips" not in self.tooltipStyle:
                self.tooltipStyle["useSystemDefaultsForTooltips"] = True

        # Apply loaded settings effects
        self.apply_loaded_settings_effects()
        
        # TEMPORARY: Also update global settings variables until Phase 3 integration
        self._update_global_settings()

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
        Apply side-effects of loading settings, especially those that interact with Qt's application state.
        """
        self.applyTooltipStyle()
        self.applyCursorFlashTime()

    def applyTooltipStyle(self):
        """
        Apply tooltip styling to the application.
        """
        if not self.tooltipStyle.get("useSystemDefaultsForTooltips", True):
            qApp.setStyleSheet(f"QToolTip {{ color: {self.tooltipStyle['textColor']}; background-color: {self.tooltipStyle['backgroundColor']}; border: 1px solid {self.tooltipStyle['borderColor']}; }}")
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

    def _update_global_settings(self):
        """
        TEMPORARY: Update global settings variables until Phase 3 integration.
        This bridges the gap between SettingsManager and the existing global variables.
        """
        from manuskript import settings as default_settings
        
        # Update global variables
        default_settings.viewSettings = self.viewSettings
        default_settings.fullscreenSettings = self.fullscreenSettings
        default_settings.dict = self.dict
        default_settings.spellcheck = self.spellcheck
        default_settings.corkSizeFactor = self.corkSizeFactor
        default_settings.folderView = self.folderView
        default_settings.lastTab = self.lastTab
        default_settings.openIndexes = self.openIndexes
        default_settings.progressChars = self.progressChars
        default_settings.countSpaces = self.countSpaces
        default_settings.autoSave = self.autoSave
        default_settings.autoSaveDelay = self.autoSaveDelay
        default_settings.saveOnQuit = self.saveOnQuit
        default_settings.autoSaveNoChanges = self.autoSaveNoChanges
        default_settings.autoSaveNoChangesDelay = self.autoSaveNoChangesDelay
        default_settings.outlineViewColumns = self.outlineViewColumns
        default_settings.corkBackground = self.corkBackground
        default_settings.corkStyle = self.corkStyle
        default_settings.fullScreenTheme = self.fullScreenTheme
        default_settings.defaultTextType = self.defaultTextType
        default_settings.textEditor = self.textEditor
        default_settings.revisions = self.revisions
        default_settings.frequencyAnalyzer = self.frequencyAnalyzer
        default_settings.viewMode = self.viewMode
        default_settings.saveToZip = self.saveToZip
        default_settings.dontShowDeleteWarning = self.dontShowDeleteWarning
        default_settings.tooltipStyle = self.tooltipStyle

    def reset_to_defaults(self):
        """
        Reset all settings to their default values.
        Used when starting a new project.
        """
        # Re-initialize all settings from defaults
        self.viewSettings = default_settings.viewSettings.copy()
        self.fullscreenSettings = default_settings.fullscreenSettings.copy()
        self.dict = default_settings.dict
        self.spellcheck = default_settings.spellcheck
        self.corkSizeFactor = default_settings.corkSizeFactor
        self.folderView = default_settings.folderView
        self.lastTab = default_settings.lastTab
        self.openIndexes = default_settings.openIndexes.copy()
        self.progressChars = default_settings.progressChars
        self.countSpaces = default_settings.countSpaces
        self.autoSave = default_settings.autoSave
        self.autoSaveDelay = default_settings.autoSaveDelay
        self.saveOnQuit = default_settings.saveOnQuit
        self.autoSaveNoChanges = default_settings.autoSaveNoChanges
        self.autoSaveNoChangesDelay = default_settings.autoSaveNoChangesDelay
        self.outlineViewColumns = default_settings.outlineViewColumns.copy()
        self.corkBackground = default_settings.corkBackground.copy()
        self.corkStyle = default_settings.corkStyle
        self.fullScreenTheme = default_settings.fullScreenTheme
        self.defaultTextType = default_settings.defaultTextType
        self.textEditor = default_settings.textEditor.copy()
        self.revisions = default_settings.revisions.copy()
        self.frequencyAnalyzer = default_settings.frequencyAnalyzer.copy()
        self.viewMode = default_settings.viewMode
        self.saveToZip = default_settings.saveToZip
        self.dontShowDeleteWarning = default_settings.dontShowDeleteWarning
        self.tooltipStyle = default_settings.tooltipStyle.copy()
        
        self.initDefaultValues()
        self._update_global_settings()
