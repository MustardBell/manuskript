#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import QWidget, QHeaderView

from manuskript.services.frequency_analysis import (
    phrase_frequencies,
    word_frequencies,
)
from manuskript.ui.tools.frequency_ui import Ui_FrequencyAnalyzer

class frequencyAnalyzer(QWidget, Ui_FrequencyAnalyzer):
    def __init__(self, outline_model, settings, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)
        self.outline_model = outline_model
        self.settings = settings

        self.splitter.setSizes([10, 100])
        self.splitter.setStretchFactor(1, 10)

        self.progressBarWord.hide()
        self.tblWord.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tblPhrase.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)


        self.btnAnalyzeWord.clicked.connect(self.analyzeWord)
        self.btnAnalyzePhrase.clicked.connect(self.analyzePhrase)

        # Settings
        self.spnWordMin.setValue(
            self.settings.frequencyAnalyzer["wordMin"]
        )
        self.txtWordExclude.setPlainText(
            self.settings.frequencyAnalyzer["wordExclude"]
        )
        self.spnPhraseMin.setValue(
            self.settings.frequencyAnalyzer["phraseMin"]
        )
        self.spnPhraseMax.setValue(
            self.settings.frequencyAnalyzer["phraseMax"]
        )
        self.spnWordMin.valueChanged.connect(self.updateSettings)
        self.txtWordExclude.textChanged.connect(self.updateSettings)
        self.spnPhraseMin.valueChanged.connect(self.updateSettings)
        self.spnPhraseMax.valueChanged.connect(self.updateSettings)

    def analyzePhrase(self):
        count = phrase_frequencies(
            self.outline_model.rootItem,
            self.spnPhraseMin.value(),
            self.spnPhraseMax.value(),
        )

        # Showing
        mdl = QStandardItemModel()
        mdl.setHorizontalHeaderLabels([self.tr("Phrases"), self.tr("Frequency")])
        for i in count.most_common():
            word = QStandardItem(" ".join(i[0]))
            number = QStandardItem()
            number.setData(i[1], Qt.DisplayRole)
            if i[1] > 1:
                mdl.appendRow([word, number])

        self.tblPhrase.setModel(mdl)

    def analyzeWord(self):
        exclude = self.txtWordExclude.toPlainText().split(",")
        count = word_frequencies(
            self.outline_model.rootItem,
            minimum_length=self.spnWordMin.value(),
            excluded=exclude,
        )

        # Showing
        mdl = QStandardItemModel()
        mdl.setHorizontalHeaderLabels([self.tr("Word"), self.tr("Frequency")])
        for i in count.most_common():
            word = QStandardItem(i[0])
            number = QStandardItem()
            number.setData(i[1], Qt.DisplayRole)
            mdl.appendRow([word, number])

        self.tblWord.setModel(mdl)

    def updateSettings(self):
        self.settings.frequencyAnalyzer[
            "wordMin"
        ] = self.spnWordMin.value()
        self.settings.frequencyAnalyzer[
            "wordExclude"
        ] = self.txtWordExclude.toPlainText()
        self.settings.frequencyAnalyzer[
            "phraseMin"
        ] = self.spnPhraseMin.value()
        self.settings.frequencyAnalyzer[
            "phraseMax"
        ] = self.spnPhraseMax.value()
