#!/usr/bin/env python
# --!-- coding: utf8 --!--

from PyQt5.QtCore import pyqtSignal

from manuskript.enums import Plot
from manuskript.models.importanceProxyModel import (
    ImportanceCategoryProxyModel,
)


class plotsProxyModel(ImportanceCategoryProxyModel):
    newStatuses = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(Plot.importance, parent)

    def mapModelMaybe(self, topLeft, bottomRight):
        self._remap_if_importance_changed(topLeft, bottomRight)

    def mapModel(self, *args):
        self.rebuild(*args)
