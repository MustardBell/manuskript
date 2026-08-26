#!/usr/bin/env python
# --!-- coding: utf8 --!--



# Because I have trouble with QDataWidgetMapper and the checkbox, I don't know why.
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QCheckBox

from manuskript.enums import Outline


class chkOutlineCompile(QCheckBox):
    def __init__(self, parent=None):
        QCheckBox.__init__(self, parent)
        self.stateChanged.connect(self.submit)
        self._column = Outline.compile
        self._index = None
        self._indexes = None
        self._model = None
        self._updating = False
        self.setAccessibleName(self.tr("Compile"))
        self.setToolTip(self.tr(
            "Include this item in compiled output. Including an item also "
            "includes its parent folders."
        ))

    def setModel(self, model):
        self._model = model
        self._model.dataChanged.connect(self.update)

    def setCurrentModelIndex(self, index):
        self._indexes = None
        if index.column() != self._column:
            index = index.sibling(index.row(), self._column)
        self._index = index
        self.setTristate(False)
        self.updateCheckState()

    def setCurrentModelIndexes(self, indexes):
        self._index = None
        self._indexes = []
        for i in indexes:
            if i.column() != self._column:
                i = i.sibling(i.row(), self._column)
            self._indexes.append(i)
        self.updateCheckState()

    def getCheckedValue(self, index):
        item = index.internalPointer()
        return Qt.Checked if item.compile() else Qt.Unchecked

    def update(self, topLeft, bottomRight):

        if self._updating:
            # We are currently putting data in the model, so no updates
            return

        if self._index:
            if topLeft.row() <= self._index.row() <= bottomRight.row():
                self.updateCheckState()

        elif self._indexes:
            update = False

            for i in self._indexes:
                if topLeft.row() <= i.row() <= bottomRight.row():
                    update = True

            if update:
                self.updateCheckState()

    def updateCheckState(self):
        self._updating = True
        try:
            if self._index:
                self.setEnabled(True)
                c = self.getCheckedValue(self._index)
                self.setCheckState(c)

            elif self._indexes:
                self.setEnabled(True)
                values = []
                for i in self._indexes:
                    values.append(self.getCheckedValue(i))

                same = True
                for v in values[1:]:
                    if v != values[0]:
                        same = False
                        break

                if same:
                    self.setCheckState(values[0])
                else:
                    self.setCheckState(Qt.PartiallyChecked)

            else:
                self.setChecked(False)
                self.setEnabled(False)
        finally:
            self._updating = False

    def submit(self, state):

        if self._updating or state == Qt.PartiallyChecked:
            return

        indexes = (
            (self._index,)
            if self._index
            else tuple(self._indexes or ())
        )
        self._updating = True
        try:
            for index in indexes:
                if self._model.data(index, Qt.CheckStateRole) != state:
                    self._model.setData(
                        index,
                        state,
                        Qt.CheckStateRole,
                    )
            self.setTristate(False)
        finally:
            self._updating = False
        self.updateCheckState()
