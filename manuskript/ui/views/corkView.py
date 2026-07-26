#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import QListView

from manuskript.settingsManager import SettingsManager
from manuskript.functions import findBackground
from manuskript.ui.views.corkDelegate import corkDelegate
from manuskript.ui.views.dndView import dndView
from manuskript.ui.views.outlineBasics import outlineBasics


class corkView(QListView, dndView, outlineBasics):
    def __init__(self, parent=None):
        QListView.__init__(self, parent)
        dndView.__init__(self, parent)
        outlineBasics.__init__(self, parent)

        self.setResizeMode(QListView.Adjust)
        self.setWrapping(True)
        self.cork_delegate = corkDelegate(self)
        self.setItemDelegate(self.cork_delegate)
        self.setSpacing(5)
        self.setVerticalScrollMode(self.ScrollPerPixel)
        self.setFlow(self.LeftToRight)
        self.setSelectionBehavior(self.SelectRows)
        self.updateBackground()

    def set_outline_context(self, context):
        outlineBasics.set_outline_context(self, context)
        self.cork_delegate.set_status_model(self.modelStatus)

    def updateBackground(self):
        if SettingsManager().corkBackground["image"] != "":
            img = findBackground(SettingsManager().corkBackground["image"])
            if img == None:
                img = ""
        else:
            # No background image
            img = ""
        self.setStyleSheet("""QListView {{
            background:{color};
            background-image: url({url});
            background-attachment: fixed;
            }}""".format(
                color=SettingsManager().corkBackground["color"],
                url=img.replace("\\", "/")
        ))

    def dragMoveEvent(self, event):
        dndView.dragMoveEvent(self, event)
        QListView.dragMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        QListView.mouseReleaseEvent(self, event)
        outlineBasics.mouseReleaseEvent(self, event)
        
    def mouseDoubleClickEvent(self, event):
        if self.selectedIndexes() == []:
            idx = self.rootIndex()
            parent = idx.parent()
            if self.outline_context is not None:
                self.outline_context.open_index(parent)
            #self.setRootIndex(parent)
        else:
            r = QListView.mouseDoubleClickEvent(self, event)
