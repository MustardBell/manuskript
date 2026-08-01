# -*- coding: utf-8 -*-

import collections

from PyQt5.QtWidgets import qApp

from manuskript.enums import Outline

# TODO: move some/all of those settings to application settings and not project settings
#       in order to allow a shared project between several writers

viewSettings = {
    "Tree": {
        "Icon": "Nothing",
        "Text": "Compile",
        "Background": "Nothing",
        "InfoFolder": "Nothing",
        "InfoText": "Nothing",
        "iconSize": 24,
        },
    "Cork": {
        "Icon": "Nothing",
        "Text": "Nothing",
        "Background": "Nothing",
        "Corner": "Label",
        "Border": "Nothing",
        },
    "Outline": {
        "Icon": "Nothing",
        "Text": "Compile",
        "Background": "Nothing",
        },
    }

fullscreenSettings = {
    "autohide-top": True,
    "autohide-bottom": True,
    "autohide-left": True,
    }

# Application
spellcheck = False
dict = None
corkSizeFactor = 100
folderView = "cork"
lastTab = 0
openIndexes = [""]
progressChars = False
countSpaces = True
autoSave = False
autoSaveDelay = 5
autoSaveNoChanges = True
autoSaveNoChangesDelay = 5
saveOnQuit = True
outlineViewColumns = [Outline.title, Outline.POV, Outline.status,
                      Outline.compile, Outline.wordCount, Outline.goal,
                      Outline.goalPercentage, Outline.label]
corkBackground = {
    "color": "#926239",
    "image": "writingdesk"
        }
corkStyle = "new"
defaultTextType = "md"
fullScreenTheme = "spacedreams"

textEditor = {
    "background": "",
    "fontColor": "",
    "font": qApp.font().toString(),
    "misspelled": "#F00",
    "lineSpacing": 100,
    "tabWidth": 20,
    "indent": False,
    "spacingAbove": 5,
    "spacingBelow": 5,
    "textAlignment": 0, # 0: left, 1: center, 2: right, 3: justify
    "cursorWidth": 1,
    "cursorNotBlinking": False,
    "maxWidth": 600,
    "marginsLR": 0,
    "marginsTB": 20,
    "backgroundTransparent": False,
    "alwaysCenter": False,
    "focusMode": False  # "line", "paragraph", "sentence"
    }

revisions = {
    "keep": False,
    "smartremove": True,
    "rules": collections.OrderedDict({
        10 * 60:            60,                     # One per minute for the last 10mn
        60 * 60:            60 * 10,                # One per 10mn for the last hour
        60 * 60 * 24:       60 * 60,                # One per hour for the last day
        60 * 60 * 24 * 30:  60 * 60 * 24,           # One per day for the last month
        None:               60 * 60 * 24 * 7,       # One per week for eternity
        })
    }

frequencyAnalyzer = {
    "wordMin": 1,
    "wordExclude": "a, and, or",
    "phraseMin": 2,
    "phraseMax": 5
}

tooltipStyle = {
    "useSystemDefaultsForTooltips": True,
    "textColor": "#000000",
    "backgroundColor": "#ffffdc",
    "borderColor": "#767676"
}

viewMode = "fiction"  # simple, fiction
saveToZip = False
dontShowDeleteWarning = False
