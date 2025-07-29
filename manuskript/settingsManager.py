import json
import logging
from PyQt5.QtWidgets import qApp

from manuskript import settings

LOGGER = logging.getLogger(__name__)

class SettingsManager:
    def __init__(self):
        pass

    def save(self, filename=None, protocol=None):
        allSettings = {
            "viewSettings": settings.viewSettings,
            "fullscreenSettings": settings.fullscreenSettings,
            "dict": settings.dict,
            "spellcheck": settings.spellcheck,
            "corkSizeFactor": settings.corkSizeFactor,
            "folderView": settings.folderView,
            "lastTab": settings.lastTab,
            "openIndexes": settings.openIndexes,
            "progressChars": settings.progressChars,
            "countSpaces": settings.countSpaces,
            "autoSave": settings.autoSave,
            "autoSaveDelay": settings.autoSaveDelay,
            "saveOnQuit": settings.saveOnQuit,
            "autoSaveNoChanges": settings.autoSaveNoChanges,
            "autoSaveNoChangesDelay": settings.autoSaveNoChangesDelay,
            "outlineViewColumns": settings.outlineViewColumns,
            "corkBackground": settings.corkBackground,
            "corkStyle": settings.corkStyle,
            "fullScreenTheme": settings.fullScreenTheme,
            "defaultTextType": settings.defaultTextType,
            "textEditor": settings.textEditor,
            "revisions": settings.revisions,
            "frequencyAnalyzer": settings.frequencyAnalyzer,
            "viewMode": settings.viewMode,
            "saveToZip": settings.saveToZip,
            "dontShowDeleteWarning": settings.dontShowDeleteWarning,
            "tooltipStyle": settings.tooltipStyle,
        }
        return json.dumps(json.loads(json.dumps(allSettings)), indent=4, sort_keys=True)

    def load(self, string, fromString=False, protocol=None):
        if not string:
            LOGGER.error("Cannot load settings.")
            return

        allSettings = json.loads(string)

        if "viewSettings" in allSettings:
            settings.viewSettings = allSettings["viewSettings"]
            for cat, name, default in [
                ("Tree", "iconSize", 24),
            ]:
                if not name in settings.viewSettings[cat]:
                    settings.viewSettings[cat][name] = default

        if "fullscreenSettings" in allSettings:
            settings.fullscreenSettings = allSettings["fullscreenSettings"]

        if "dict" in allSettings:
            settings.dict = allSettings["dict"]

        if "spellcheck" in allSettings:
            settings.spellcheck = allSettings["spellcheck"]

        if "corkSizeFactor" in allSettings:
            settings.corkSizeFactor = allSettings["corkSizeFactor"]

        if "folderView" in allSettings:
            settings.folderView = allSettings["folderView"]

        if "lastTab" in allSettings:
            settings.lastTab = allSettings["lastTab"]

        if "openIndexes" in allSettings:
            settings.openIndexes = allSettings["openIndexes"]

        if "progressChars" in allSettings:
            settings.progressChars = allSettings["progressChars"]

        if "countSpaces" in allSettings:
            settings.countSpaces = allSettings["countSpaces"]

        if "autoSave" in allSettings:
            settings.autoSave = allSettings["autoSave"]

        if "autoSaveDelay" in allSettings:
            settings.autoSaveDelay = allSettings["autoSaveDelay"]

        if "saveOnQuit" in allSettings:
            settings.saveOnQuit = allSettings["saveOnQuit"]

        if "autoSaveNoChanges" in allSettings:
            settings.autoSaveNoChanges = allSettings["autoSaveNoChanges"]

        if "autoSaveNoChangesDelay" in allSettings:
            settings.autoSaveNoChangesDelay = allSettings["autoSaveNoChangesDelay"]

        if "outlineViewColumns" in allSettings:
            settings.outlineViewColumns = allSettings["outlineViewColumns"]

        if "corkBackground" in allSettings:
            settings.corkBackground = allSettings["corkBackground"]

        if "corkStyle" in allSettings:
            settings.corkStyle = allSettings["corkStyle"]

        if "fullScreenTheme" in allSettings:
            settings.fullScreenTheme = allSettings["fullScreenTheme"]

        if "defaultTextType" in allSettings:
            settings.defaultTextType = allSettings["defaultTextType"]

        if "textEditor" in allSettings:
            settings.textEditor = allSettings["textEditor"]
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
                if not k in settings.textEditor: settings.textEditor[k] = added[k]
            if settings.textEditor["cursorNotBlinking"]:
                qApp.setCursorFlashTime(0)
            else:
                from manuskript.functions import mainWindow
                qApp.setCursorFlashTime(mainWindow()._defaultCursorFlashTime)

        if "revisions" in allSettings:
            settings.revisions = allSettings["revisions"]
            r = {}
            for i in settings.revisions["rules"]:
                if i == "null":
                    r[None] = settings.revisions["rules"]["null"]
                elif i == None:
                    r[None] = settings.revisions["rules"][None]
                else:
                    r[int(i)] = settings.revisions["rules"][i]
            settings.revisions["rules"] = r

        if "frequencyAnalyzer" in allSettings:
            settings.frequencyAnalyzer = allSettings["frequencyAnalyzer"]

        if "viewMode" in allSettings:
            settings.viewMode = allSettings["viewMode"]

        if "saveToZip" in allSettings:
            settings.saveToZip = allSettings["saveToZip"]

        if "dontShowDeleteWarning" in allSettings:
            settings.dontShowDeleteWarning = allSettings["dontShowDeleteWarning"]

        if "tooltipStyle" in allSettings:
            settings.tooltipStyle = allSettings["tooltipStyle"]
            if "useSystemDefaultsForTooltips" not in settings.tooltipStyle:
                settings.tooltipStyle["useSystemDefaultsForTooltips"] = True
