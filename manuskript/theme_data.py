import os

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import qApp


def loadThemeDatas(themeFile):
    settings = QSettings(themeFile, QSettings.IniFormat)
    theme_data = {"Name": getThemeName(themeFile)}

    for key, default in [
        ("Background/Color", "#000000"),
        ("Background/ImageFile", ""),
        ("Background/Type", 0),
        ("Foreground/Color", "#ffffff"),
        ("Foreground/Opacity", 50),
        ("Foreground/Margin", 40),
        ("Foreground/Padding", 10),
        ("Foreground/Position", 1),
        ("Foreground/Rounding", 5),
        ("Foreground/Width", 700),
        ("Text/Color", "#ffffff"),
        ("Text/Font", qApp.font().toString()),
        ("Text/Misspelled", "#ff0000"),
        ("Spacings/Alignment", 0),
        ("Spacings/IndentFirstLine", False),
        ("Spacings/LineSpacing", 100),
        ("Spacings/ParagraphAbove", 0),
        ("Spacings/ParagraphBelow", 0),
        ("Spacings/TabWidth", 48),
    ]:
        theme_data[key] = settings.value(
            key,
            default,
            type(default),
        )

    return theme_data


def getThemeName(theme):
    settings = QSettings(theme, QSettings.IniFormat)
    if settings.contains("Name"):
        return settings.value("Name")
    return os.path.splitext(os.path.basename(theme))[0]
