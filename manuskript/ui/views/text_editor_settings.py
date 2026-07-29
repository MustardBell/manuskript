from PyQt5.QtWidgets import qApp


class DefaultTextEditorSettings:
    """Safe local settings for text widgets before application composition."""

    def __init__(self):
        self.spellcheck = False
        self.dict = None
        self.textEditor = {
            "background": "",
            "fontColor": "",
            "font": qApp.font().toString(),
            "misspelled": "#F00",
            "lineSpacing": 100,
            "tabWidth": 20,
            "indent": False,
            "spacingAbove": 5,
            "spacingBelow": 5,
            "textAlignment": 0,
            "cursorWidth": 1,
            "cursorNotBlinking": False,
            "maxWidth": 600,
            "marginsLR": 0,
            "marginsTB": 20,
            "backgroundTransparent": False,
            "alwaysCenter": False,
            "focusMode": False,
            "markdownMode": "live-preview",
        }
