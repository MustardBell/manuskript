#!/usr/bin/env python
# --!-- coding: utf8 --!--
import importlib
import os
import re

from PyQt5.Qt import qVersion, PYQT_VERSION_STR
from PyQt5.QtCore import (pyqtSignal, QSignalMapper, QTimer, QSettings, Qt, QPoint,
                          QRegExp, QUrl, QSize)
from PyQt5.QtGui import QIcon, QColor
from PyQt5.QtWidgets import QMainWindow, qApp, QMenu, QActionGroup, QAction, QStyle, QListWidgetItem, \
    QLabel, QDockWidget, QWidget, QMessageBox, QLineEdit, QTextEdit, QTreeView, QTableView

from manuskript.controllers.character_controller import CharacterController
from manuskript.controllers.plot_controller import PlotController
from manuskript.settingsManager import SettingsManager
from manuskript.enums import Character, PlotStep, Plot, World, Outline
from manuskript.functions import wordCount, appPath, findWidgetsOfClass, openURL, showInFolder
import manuskript.functions as F
from manuskript import loadSave
from manuskript.functions.history.History import History
from manuskript.logging import getLogFilePath
from manuskript.models.characterModel import characterModel
from manuskript.models import outlineModel
from manuskript.models.plotModel import plotModel
from manuskript.models.worldModel import worldModel
from manuskript.projectManager import ProjectManager
from manuskript.settingsWindow import settingsWindow
from manuskript.ui import style
from manuskript.ui.about import aboutDialog
from manuskript.ui.collapsibleDockWidgets import collapsibleDockWidgets
from manuskript.ui.connections import SignalConnectionRegistry
from manuskript.ui.importers.importer import importerDialog
from manuskript.ui.exporters.exporter import exporterDialog
from manuskript.ui.helpLabel import helpLabel
from manuskript.ui.mainWindow import Ui_MainWindow
from manuskript.ui.tools.frequencyAnalyzer import frequencyAnalyzer
from manuskript.ui.tools.targets import TargetsDialog
from manuskript.ui.views.outlineDelegates import outlineCharacterDelegate
from manuskript.ui.views.plotDelegate import plotDelegate
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.statusLabel import statusLabel

# Spellcheck support
from manuskript.ui.views.textEditView import textEditView
from manuskript.functions import Spellchecker

import logging
LOGGER = logging.getLogger(__name__)

class MainWindow(QMainWindow, Ui_MainWindow):
    # dictChanged = pyqtSignal(str)

    # Tab indexes
    TabInfos = 0
    TabSummary = 1
    TabPersos = 2
    TabPlots = 3
    TabWorld = 4
    TabOutline = 5
    TabRedac = 6
    TabDebug = 7

    SHOW_DEBUG_TAB = False

    def __init__(self):
        QMainWindow.__init__(self)
        self.setupUi(self)

        # Var
        self._lastFocus = None
        self._lastMDEditView = None
        self._defaultCursorFlashTime = 1000 # Overridden at startup with system
                                            # value. In manuskript.main.
        self._autoLoadProject = None  # Used to load a command line project
        self.sessionStartWordCount = 0  # Used to track session targets
        self.history = History()
        self._previousSelectionEmpty = True
        self.projectConnections = SignalConnectionRegistry()
        self.characterController = CharacterController(self)
        self.plotController = PlotController(self)
        self.projectManager = ProjectManager(self)
        self.settingsManager = SettingsManager()

        self.readSettings()

        # UI
        self.setupMoreUi()
        self.statusLabel = statusLabel(parent=self)
        self.statusLabel.setAutoFillBackground(True)
        self.statusLabel.hide()

        # Welcome
        self.welcome.updateValues()
        self.switchToWelcome()

        # Word count
        self.mprWordCount = QSignalMapper(self)
        for t, i in [
            (self.txtSummarySentence, 0),
            (self.txtSummaryPara, 1),
            (self.txtSummaryPage, 2),
            (self.txtSummaryFull, 3)
        ]:
            t.textChanged.connect(self.mprWordCount.map)
            self.mprWordCount.setMapping(t, i)
        self.mprWordCount.mapped.connect(self.wordCount)

        self.cmbSummary.setCurrentIndex(0)
        self.cmbSummary.currentIndexChanged.emit(0)

        # Main Menu
        self.projectManager.syncUiToState()

        # Main Menu:: File
        self.actOpen.triggered.connect(self.welcome.openFile)
        self.actSave.triggered.connect(self.projectManager.saveDatas)
        self.actSaveAs.triggered.connect(self.welcome.saveAsFile)
        self.actImport.triggered.connect(self.doImport)
        self.actCompile.triggered.connect(self.doCompile)
        self.actCloseProject.triggered.connect(self.projectManager.closeProject)
        self.actQuit.triggered.connect(self.close)

        # Main menu:: Edit
        self.actCopy.triggered.connect(self.documentsCopy)
        self.actCut.triggered.connect(self.documentsCut)
        self.actPaste.triggered.connect(self.documentsPaste)
        self.actSearch.triggered.connect(self.doSearch)
        self.actRename.triggered.connect(self.documentsRename)
        self.actDuplicate.triggered.connect(self.documentsDuplicate)
        self.actDelete.triggered.connect(self.documentsDelete)
        self.actLabels.triggered.connect(self.settingsLabel)
        self.actStatus.triggered.connect(self.settingsStatus)
        self.actSettings.triggered.connect(self.settingsWindow)

        # Main menu:: Edit:: Format
        self.actHeaderSetextL1.triggered.connect(self.formatSetext1)
        self.actHeaderSetextL2.triggered.connect(self.formatSetext2)
        self.actHeaderAtxL1.triggered.connect(self.formatAtx1)
        self.actHeaderAtxL2.triggered.connect(self.formatAtx2)
        self.actHeaderAtxL3.triggered.connect(self.formatAtx3)
        self.actHeaderAtxL4.triggered.connect(self.formatAtx4)
        self.actHeaderAtxL5.triggered.connect(self.formatAtx5)
        self.actHeaderAtxL6.triggered.connect(self.formatAtx6)
        self.actFormatBold.triggered.connect(self.formatBold)
        self.actFormatItalic.triggered.connect(self.formatItalic)
        self.actFormatStrike.triggered.connect(self.formatStrike)
        self.actFormatVerbatim.triggered.connect(self.formatVerbatim)
        self.actFormatSuperscript.triggered.connect(self.formatSuperscript)
        self.actFormatSubscript.triggered.connect(self.formatSubscript)
        self.actFormatCommentLines.triggered.connect(self.formatCommentLines)
        self.actFormatList.triggered.connect(self.formatList)
        self.actFormatOrderedList.triggered.connect(self.formatOrderedList)
        self.actFormatBlockquote.triggered.connect(self.formatBlockquote)
        self.actFormatCommentBlock.triggered.connect(self.formatCommentBlock)
        self.actFormatClear.triggered.connect(self.formatClear)

        # Main menu:: Organize
        self.actMoveUp.triggered.connect(self.documentsMoveUp)
        self.actMoveDown.triggered.connect(self.documentsMoveDown)
        self.actSplitDialog.triggered.connect(self.documentsSplitDialog)
        self.actSplitCursor.triggered.connect(self.documentsSplitCursor)
        self.actMerge.triggered.connect(self.documentsMerge)

        # Main menu:: Navigate
        self.actBack.triggered.connect(self.navigateBack)
        self.actForward.triggered.connect(self.navigateForward)

        # Main Menu:: view
        self.generateViewMenu()
        self.actModeGroup = QActionGroup(self)
        self.actModeSimple.setActionGroup(self.actModeGroup)
        self.actModeFiction.setActionGroup(self.actModeGroup)
        self.actModeSimple.triggered.connect(self.setViewModeSimple)
        self.actModeFiction.triggered.connect(self.setViewModeFiction)

        # Main Menu:: Tool
        self.actToolFrequency.triggered.connect(self.frequencyAnalyzer)
        self.actToolTargets.triggered.connect(self.sessionTargets)
        self.actSupport.triggered.connect(self.support)
        self.actLocateLog.triggered.connect(self.locateLogFile)
        self.actAbout.triggered.connect(self.about)

        self.makeUIConnections()

        # Tools non-modal windows
        self.td = None  # Targets Dialog
        self.fw = None  # Frequency Window

        self.characterController.capture_tabs()

    @property
    def currentProject(self):
        """Compatibility view of the active project path."""
        return self.projectManager.currentProject

    @property
    def projectDirty(self):
        """Compatibility view of whether the active project has unsaved changes."""
        return self.projectManager.projectDirty

    def updateDockVisibility(self, restore=False):
        """
        Saves the state of the docks visibility. Or if `restore` is True,
        restores from `self._dckVisibility`. This allows to hide the docks
        while showing the welcome screen, and then restore them as they
        were.

        If `self._dckVisibility` contains "LOCK", then we don't override values
        with current visibility state. This is used the first time we load.
        "LOCK" is then removed.
        """
        docks = [
            self.dckCheatSheet,
            self.dckNavigation,
            self.dckSearch,
        ]

        for d in docks:
            if not restore:
                # We store the values, but only if "LOCK" is not present
                if not "LOCK" in self._dckVisibility:
                    self._dckVisibility[d.objectName()] = d.isVisible()
                # Hide the dock
                d.setVisible(False)
            else:
                # Restore the dock's visibility based on stored value
                d.setVisible(self._dckVisibility[d.objectName()])

        # Lock is used only once, at start up. We can remove it
        if "LOCK" in self._dckVisibility:
            self._dckVisibility.pop("LOCK")

    def switchToWelcome(self):
        """
        While switching to welcome screen, we have to hide all the docks.
        Otherwise one could use the search dock, and manuskript would crash.
        Plus it's unnecessary distraction.
        But we also want to restore them to their visibility prior to switching,
        so we store states.
        """
        # Stores the state of docks
        self.updateDockVisibility()
        # Hides the toolbar
        self.toolbar.setVisible(False)
        # Switch to welcome screen
        self.stack.setCurrentIndex(0)

    def switchToProject(self):
        """Restores docks and toolbar visibility, and switch to project."""
        # Restores the docks visibility
        self.updateDockVisibility(restore=True)
        # Show the toolbar
        self.toolbar.setVisible(True)
        self.stack.setCurrentIndex(1)

    def closeEvent(self, event):
        """Close the application only after the project closes safely."""
        if not self.projectManager.closeProject():
            event.ignore()
            return
        super().closeEvent(event)

    ###############################################################################
    # GENERAL / UI STUFF
    ###############################################################################

    def tabMainChanged(self):
        "Called when main tab changes."
        tabIsEditor = self.tabMain.currentIndex() == self.TabRedac
        self.menuOrganize.menuAction().setEnabled(tabIsEditor)
        for i in [self.actCut,
                  self.actCopy,
                  self.actPaste,
                  self.actDelete,
                  self.actRename]:
            i.setEnabled(tabIsEditor)
        tabIndex = self.tabMain.currentIndex()

        if tabIndex == self.TabPersos:
            self.characterController.record_current_selection()
        elif tabIndex == self.TabPlots:
            self.plotController.record_current_selection()
        elif tabIndex == self.TabWorld:
            index = self.mdlWorld.selectedIndex()

            if index.isValid():
                id = self.mdlWorld.ID(index)
                self.pushHistory(("world", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("world", None))
                self._previousSelectionEmpty = True
        elif tabIndex == self.TabOutline:
            index = self.treeOutlineOutline.selectionModel().currentIndex()
            if index.isValid():
                id = self.mdlOutline.ID(index)
                self.pushHistory(("outline", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("outline", None))
                self._previousSelectionEmpty = False
        elif tabIndex == self.TabRedac:
            index = self.treeRedacOutline.selectionModel().currentIndex()
            if index.isValid():
                id = self.mdlOutline.ID(index)
                self.pushHistory(("redac", id))
                self._previousSelectionEmpty = id is not None
            else:
                self.pushHistory(("redac", None))
                self._previousSelectionEmpty = False
        else:
            self.pushHistory(("main", self.tabMain.currentIndex()))
            self._previousSelectionEmpty = False

    def focusChanged(self, old, new):
        """
        We get notified by qApp when focus changes, from old to new widget.
        """

        # If new is a MDEditView, we keep it in memory
        if issubclass(type(new), MDEditView):
            self._lastMDEditView = new
        else:
            self._lastMDEditView = None

        # Determine which view had focus last, to send the keyboard shortcuts
        # to the right place

        targets = [
            self.treeRedacOutline,
            self.mainEditor
        ]

        while new is not None:
            if new in targets:
                self._lastFocus = new
                break
            new = new.parent()

    def projectName(self):
        """
        Returns a user-friendly name for the loaded project.
        """
        pName = os.path.split(self.currentProject)[1]
        if pName.endswith('.msk'):
            pName=pName[:-4]
        return pName

    ###############################################################################
    # OUTLINE
    ###############################################################################

    def outlineChanged(self, selected, deselected):
        index = self.treeOutlineOutline.selectionModel().currentIndex()
        if not index.isValid():
            self.pushHistory(("outline", None))
            self._previousSelectionEmpty = True
            return
        
        self.pushHistory(("outline", self.mdlOutline.ID(index)))
        self._previousSelectionEmpty = False


    def outlineRemoveItemsRedac(self):
        self.treeRedacOutline.delete()

    def outlineRemoveItemsOutline(self):
        self.treeOutlineOutline.delete()

    ###############################################################################
    # WORLD
    ###############################################################################

    def changeCurrentWorld(self):
        index = self.mdlWorld.selectedIndex()

        if not index.isValid():
            self.tabWorld.setEnabled(False)
            self.pushHistory(("world", None))
            self._previousSelectionEmpty = True
            return

        self.pushHistory(("world", self.mdlWorld.ID(index)))
        self._previousSelectionEmpty = False

        self.tabWorld.setEnabled(True)
        self.txtWorldName.setCurrentModelIndex(index)
        self.txtWorldDescription.setCurrentModelIndex(index)
        self.txtWorldPassion.setCurrentModelIndex(index)
        self.txtWorldConflict.setCurrentModelIndex(index)

    ###############################################################################
    # EDITOR
    ###############################################################################

    def redacOutlineChanged(self):
        index = self.treeRedacOutline.selectionModel().currentIndex()
        if not index.isValid():
            self.pushHistory(("redac", None))
            self._previousSelectionEmpty = True
            return
        
        self.pushHistory(("redac", self.mdlOutline.ID(index)))
        self._previousSelectionEmpty = False

    def openIndex(self, index):
        self.treeRedacOutline.setCurrentIndex(index)

    def openIndexes(self, indexes, newTab=True):
        self.mainEditor.openIndexes(indexes, newTab=True)

    # Menu #############################################################

    # Functions called by the menus
    # self._lastFocus is the last editor that had focus (either treeView or
    # mainEditor). So we just pass along the signal.

    # Edit

    def documentsCopy(self):
        "Copy selected item(s)."
        if self._lastFocus: self._lastFocus.copy()
    def documentsCut(self):
        "Cut selected item(s)."
        if self._lastFocus: self._lastFocus.cut()
    def documentsPaste(self):
        "Paste clipboard item(s) into selected item."
        if self._lastFocus: self._lastFocus.paste()
    def doSearch(self):
        "Do a global search."
        self.dckSearch.show()
        self.dckSearch.activateWindow()
        searchTextInput = self.dckSearch.findChild(QLineEdit, 'searchTextInput')
        searchTextInput.setFocus()
        searchTextInput.selectAll()
    def documentsRename(self):
        "Rename selected item."
        if self._lastFocus: self._lastFocus.rename()
    def documentsDuplicate(self):
        "Duplicate selected item(s)."
        if self._lastFocus: self._lastFocus.duplicate()
    def documentsDelete(self):
        "Delete selected item(s)."
        if self._lastFocus: self._lastFocus.delete()

    # Formats
    def callLastMDEditView(self, functionName, param=[]):
        """
        If last focused widget was MDEditView, call the given function.
        """
        if self._lastMDEditView:
            function = getattr(self._lastMDEditView, functionName)
            function(*param)
    def formatSetext1(self): self.callLastMDEditView("titleSetext", [1])
    def formatSetext2(self): self.callLastMDEditView("titleSetext", [2])
    def formatAtx1(self): self.callLastMDEditView("titleATX", [1])
    def formatAtx2(self): self.callLastMDEditView("titleATX", [2])
    def formatAtx3(self): self.callLastMDEditView("titleATX", [3])
    def formatAtx4(self): self.callLastMDEditView("titleATX", [4])
    def formatAtx5(self): self.callLastMDEditView("titleATX", [5])
    def formatAtx6(self): self.callLastMDEditView("titleATX", [6])
    def formatBold(self): self.callLastMDEditView("bold")
    def formatItalic(self): self.callLastMDEditView("italic")
    def formatStrike(self): self.callLastMDEditView("strike")
    def formatVerbatim(self): self.callLastMDEditView("verbatim")
    def formatSuperscript(self): self.callLastMDEditView("superscript")
    def formatSubscript(self): self.callLastMDEditView("subscript")
    def formatCommentLines(self): self.callLastMDEditView("commentLine")
    def formatList(self): self.callLastMDEditView("unorderedList")
    def formatOrderedList(self): self.callLastMDEditView("orderedList")
    def formatBlockquote(self): self.callLastMDEditView("blockquote")
    def formatCommentBlock(self): self.callLastMDEditView("comment")
    def formatClear(self): self.callLastMDEditView("clearFormat")

    # Organize

    def documentsMoveUp(self):
        "Move up selected item(s)."
        if self._lastFocus: self._lastFocus.moveUp()
    def documentsMoveDown(self):
        "Move Down selected item(s)."
        if self._lastFocus: self._lastFocus.moveDown()

    def documentsSplitDialog(self):
        "Opens a dialog to split selected items."
        if self._lastFocus: self._lastFocus.splitDialog()
        # current items or selected items?
        pass
        # use outlineBasics, to do that on all selected items.
        # use editorWidget to do that on selected text.

    def documentsSplitCursor(self):
        """
        Split current item (open in text editor) at cursor position. If there is
        a text selection, that selection becomes the title of the new scene.
        """
        if self._lastFocus and self._lastFocus == self.mainEditor:
            self.mainEditor.splitCursor()
    def documentsMerge(self):
        "Merges selected item(s)."
        if self._lastFocus: self._lastFocus.merge()

    # Navigate
    
    def navigateBack(self):
        self.history.back()

    def navigateForward(self):
        self.history.forward()

    def pushHistory(self, entry):
        if self._previousSelectionEmpty:
            self.history.replace(entry)
        else:
            self.history.next(entry)

    def navigated(self, event):
        if event.entry:
            first_entry = event.entry[0]

            if first_entry == "character":
                if self.tabMain.currentIndex() != self.TabPersos:
                    self.tabMain.setCurrentIndex(self.TabPersos)

                if event.entry[1] is None:
                    self.lstCharacters.setCurrentItem(None)
                    self.lstCharacters.clearSelection()
                else:
                    if self.lstCharacters.currentCharacterID() != event.entry[1]:
                        char = self.lstCharacters.getItemByID(event.entry[1])
                        if char != None:
                            self.lstCharacters.clearSelection()
                            self.lstCharacters.setCurrentItem(char)
            elif first_entry == "plot":
                if self.tabMain.currentIndex() != self.TabPlots:
                    self.tabMain.setCurrentIndex(self.TabPlots)

                if event.entry[1] is None:
                    self.lstPlots.setCurrentItem(None)
                else:
                    index = self.lstPlots.currentPlotIndex()
                    if index and index.row() != event.entry[1]:
                        plot = self.lstPlots.getItemByID(event.entry[1])
                        if plot != None:
                            self.lstPlots.setCurrentItem(plot)
            elif first_entry == "world":
                if self.tabMain.currentIndex() != self.TabWorld:
                    self.tabMain.setCurrentIndex(self.TabWorld)

                if event.entry[1] is None:
                    self.treeWorld.selectionModel().clear()
                else:
                    index = self.mdlWorld.selectedIndex()
                    if index and self.mdlWorld.ID(index) != event.entry[1]:
                        world = self.mdlWorld.indexByID(event.entry[1])
                        if world != None:
                            self.treeWorld.setCurrentIndex(world)
            elif first_entry == "outline":
                if self.tabMain.currentIndex() != self.TabOutline:
                    self.tabMain.setCurrentIndex(self.TabOutline)

                if event.entry[1] is None:
                    self.treeOutlineOutline.selectionModel().clear()
                else:
                    index = self.treeOutlineOutline.selectionModel().currentIndex()
                    if index and self.mdlOutline.ID(index) != event.entry[1]:
                        outline = self.mdlOutline.getIndexByID(event.entry[1])
                        if outline is not None:
                            self.treeOutlineOutline.setCurrentIndex(outline)
            elif first_entry == "redac":
                if self.tabMain.currentIndex() != self.TabRedac:
                    self.tabMain.setCurrentIndex(self.TabRedac)

                if event.entry[1] is None:
                    self.treeRedacOutline.selectionModel().clear()
                else:
                    index = self.treeRedacOutline.selectionModel().currentIndex()
                    if index and self.mdlOutline.ID(index) != event.entry[1]:
                        outline = self.mdlOutline.getIndexByID(event.entry[1])
                        if outline is not None:
                            self.treeRedacOutline.setCurrentIndex(outline)
            elif first_entry == "main":
                if self.tabMain.currentIndex() != event.entry[1]:
                    self.lstTabs.setCurrentRow(event.entry[1])

        self.actBack.setEnabled(event.position > 0)
        self.actForward.setEnabled(event.position < event.count - 1)

    def readSettings(self):
        # Load State and geometry
        sttgns = QSettings(qApp.organizationName(), qApp.applicationName())
        if sttgns.contains("geometry"):
            self.restoreGeometry(sttgns.value("geometry"))
        if sttgns.contains("windowState"):
            self.restoreState(sttgns.value("windowState"))

        if sttgns.contains("docks"):
            self._dckVisibility = {}
            vals = sttgns.value("docks")
            for name in vals:
                self._dckVisibility[name] = vals[name]
        else:
            # Create default settings
            self._dckVisibility = {
                self.dckNavigation.objectName() : True,
                self.dckCheatSheet.objectName() : False,
                self.dckSearch.objectName() : False,
            }
        self._dckVisibility["LOCK"] = True  # prevent overriding loaded values

        if sttgns.contains("metadataState"):
            state = [False if v == "false" else True for v in sttgns.value("metadataState")]
            self.redacMetadata.restoreState(state)
        if sttgns.contains("revisionsState"):
            state = [False if v == "false" else True for v in sttgns.value("revisionsState")]
            self.redacMetadata.revisions.restoreState(state)
        if sttgns.contains("splitterRedacH"):
            self.splitterRedacH.restoreState(sttgns.value("splitterRedacH"))
        if sttgns.contains("splitterRedacV"):
            self.splitterRedacV.restoreState(sttgns.value("splitterRedacV"))
        if sttgns.contains("toolbar"):
            # self.toolbar is not initialized yet, so we just store value
            self._toolbarState = sttgns.value("toolbar")
        else:
            self._toolbarState = ""

    ###############################################################################
    # MAIN CONNECTIONS
    ###############################################################################

    def makeUIConnections(self):
        "Connections that have to be made once only, even when a new project is loaded."
        # Characters
        self.txtPersosFilter.textChanged.connect(self.lstCharacters.setFilter, F.AUC)
        self.lstCharacters.itemSelectionChanged.connect(
            self.characterController.handle_selection_changed,
            F.AUC,
        )

        # Plots
        self.txtPlotFilter.textChanged.connect(self.lstPlots.setFilter, F.AUC)
        self.lstPlots.currentItemChanged.connect(
            self.plotController.handle_plot_selection_changed,
            F.AUC,
        )

        # Outline
        self.btnRedacAddFolder.clicked.connect(self.treeRedacOutline.addFolder, F.AUC)
        self.btnOutlineAddFolder.clicked.connect(self.treeOutlineOutline.addFolder, F.AUC)
        self.btnRedacAddText.clicked.connect(self.treeRedacOutline.addText, F.AUC)
        self.btnOutlineAddText.clicked.connect(self.treeOutlineOutline.addText, F.AUC)
        self.btnRedacRemoveItem.clicked.connect(self.outlineRemoveItemsRedac, F.AUC)
        self.btnOutlineRemoveItem.clicked.connect(self.outlineRemoveItemsOutline, F.AUC)

        self.tabMain.currentChanged.connect(self.toolbar.setCurrentGroup)
        self.tabMain.currentChanged.connect(self.tabMainChanged)

        self.history.navigated.connect(self.navigated)

        qApp.focusChanged.connect(self.focusChanged)

    def makeConnections(self):
        if self.projectConnections:
            raise RuntimeError(
                "Project connections must be released before binding new models."
            )
        connect = self.projectConnections.connect

        # Flat datas (Summary and general infos)
        for widget, col in [
            (self.txtSummarySituation, 0),
            (self.txtSummarySentence, 1),
            (self.txtSummarySentence_2, 1),
            (self.txtSummaryPara, 2),
            (self.txtSummaryPara_2, 2),
            (self.txtPlotSummaryPara, 2),
            (self.txtSummaryPage, 3),
            (self.txtSummaryPage_2, 3),
            (self.txtPlotSummaryPage, 3),
            (self.txtSummaryFull, 4),
            (self.txtPlotSummaryFull, 4),
        ]:
            widget.setModel(self.mdlFlatData)
            widget.setColumn(col)
            widget.setCurrentModelIndex(self.mdlFlatData.index(1, col))

        for widget, col in [
            (self.txtGeneralTitle, 0),
            (self.txtGeneralSubtitle, 1),
            (self.txtGeneralSerie, 2),
            (self.txtGeneralVolume, 3),
            (self.txtGeneralGenre, 4),
            (self.txtGeneralLicense, 5),
            (self.txtGeneralAuthor, 6),
            (self.txtGeneralEmail, 7),
        ]:
            widget.setModel(self.mdlFlatData)
            widget.setColumn(col)
            widget.setCurrentModelIndex(self.mdlFlatData.index(0, col))

        # Characters
        self.characterController.configure_info_view(self.tblPersoInfos)
        self.lstCharacters.setCharactersModel(self.mdlCharacter)
        self.tblPersoInfos.setModel(self.mdlCharacter)
        connect(
            self.btnAddPerso.clicked,
            self.lstCharacters.addCharacter,
            F.AUC,
        )
        connect(
            self.btnRmPerso.clicked,
            self.characterController.delete_characters,
            F.AUC,
        )
        connect(
            self.btnPersoColor.clicked,
            self.characterController.choose_character_color,
            F.AUC,
        )
        connect(
            self.chkPersoPOV.stateChanged,
            self.characterController.change_character_pov_state,
            F.AUC,
        )
        connect(
            self.btnPersoAddInfo.clicked,
            self.characterController.add_character_info,
            F.AUC,
        )
        connect(
            self.btnPersoRmInfo.clicked,
            self.characterController.remove_character_info,
            F.AUC,
        )

        for w, c in [
            (self.txtPersoName, Character.name),
            (self.sldPersoImportance, Character.importance),
            (self.txtPersoMotivation, Character.motivation),
            (self.txtPersoGoal, Character.goal),
            (self.txtPersoConflict, Character.conflict),
            (self.txtPersoEpiphany, Character.epiphany),
            (self.txtPersoSummarySentence, Character.summarySentence),
            (self.txtPersoSummaryPara, Character.summaryPara),
            (self.txtPersoSummaryFull, Character.summaryFull),
            (self.txtPersoNotes, Character.notes)
        ]:
            w.setModel(self.mdlCharacter)
            w.setColumn(c)
        self.tabPersos.setEnabled(False)

        # Plots
        self.lstSubPlots.setModel(self.mdlPlots)
        self.lstPlotPerso.setModel(self.mdlPlots)
        self.lstPlots.setPlotModel(self.mdlPlots)
        connect(self.btnAddPlot.clicked, self.plotController.add_plot, F.AUC)
        connect(
            self.btnRmPlot.clicked,
            self.plotController.remove_current_plot,
            F.AUC,
        )
        connect(
            self.btnAddSubPlot.clicked,
            self.plotController.add_sub_plot,
            F.AUC,
        )
        connect(
            self.btnRmSubPlot.clicked,
            self.plotController.remove_selected_sub_plots,
            F.AUC,
        )
        connect(
            self.lstPlotPerso.selectionModel().selectionChanged,
            self.plotController.handle_plot_character_selection,
        )
        connect(
            self.btnRmPlotPerso.clicked,
            self.plotController.remove_selected_plot_characters,
            F.AUC,
        )
        connect(
            self.lstSubPlots.selectionModel().currentRowChanged,
            self.plotController.change_current_sub_plot,
            F.AUC,
        )

        for w, c in [
            (self.txtPlotName, Plot.name),
            (self.txtPlotDescription, Plot.description),
            (self.txtPlotResult, Plot.result),
            (self.sldPlotImportance, Plot.importance),
        ]:
            w.setModel(self.mdlPlots)
            w.setColumn(c)

        self.tabPlot.setEnabled(False)
        self.plotController.refresh_character_menu()
        connect(
            self.mdlCharacter.dataChanged,
            self.plotController.refresh_character_menu,
        )
        self.lstOutlinePlots.setPlotModel(self.mdlPlots)
        self.lstOutlinePlots.setShowSubPlot(True)
        self.plotCharacterDelegate = outlineCharacterDelegate(self.mdlCharacter, self)
        self.lstPlotPerso.setItemDelegate(self.plotCharacterDelegate)
        self.plotDelegate = plotDelegate(self)
        self.lstSubPlots.setItemDelegateForColumn(PlotStep.meta, self.plotDelegate)

        # World
        self.treeWorld.setModel(self.mdlWorld)
        for i in range(self.mdlWorld.columnCount()):
            self.treeWorld.hideColumn(i)
        self.treeWorld.showColumn(0)
        self.btnWorldEmptyData.setMenu(self.mdlWorld.emptyDataMenu())
        connect(
            self.treeWorld.selectionModel().selectionChanged,
            self.changeCurrentWorld,
            F.AUC,
        )
        connect(self.btnAddWorld.clicked, self.mdlWorld.addItem, F.AUC)
        connect(self.btnRmWorld.clicked, self.mdlWorld.removeItem, F.AUC)
        for w, c in [
            (self.txtWorldName, World.name),
            (self.txtWorldDescription, World.description),
            (self.txtWorldPassion, World.passion),
            (self.txtWorldConflict, World.conflict),
        ]:
            w.setModel(self.mdlWorld)
            w.setColumn(c)
        self.tabWorld.setEnabled(False)
        self.treeWorld.expandAll()

        # Outline
        self.treeRedacOutline.setModel(self.mdlOutline)
        self.treeOutlineOutline.setModelCharacters(self.mdlCharacter)
        self.treeOutlineOutline.setModelLabels(self.mdlLabels)
        self.treeOutlineOutline.setModelStatus(self.mdlStatus)

        self.redacMetadata.setModels(self.mdlOutline, self.mdlCharacter,
                                     self.mdlLabels, self.mdlStatus)
        self.outlineItemEditor.setModels(self.mdlOutline, self.mdlCharacter,
                                         self.mdlLabels, self.mdlStatus)

        self.treeOutlineOutline.setModel(self.mdlOutline)
        # self.redacEditor.setModel(self.mdlOutline)
        self.storylineView.setModels(self.mdlOutline, self.mdlCharacter, self.mdlPlots)

        connect(
            self.treeOutlineOutline.selectionModel().selectionChanged,
            self.outlineChanged,
            F.AUC,
        )
        connect(
            self.treeOutlineOutline.selectionModel().selectionChanged,
            self.outlineItemEditor.selectionChanged,
            F.AUC,
        )
        connect(
            self.treeOutlineOutline.clicked,
            self.outlineItemEditor.selectionChanged,
            F.AUC,
        )

        # Sync selection
        connect(
            self.treeRedacOutline.selectionModel().selectionChanged,
            self.redacOutlineChanged,
            F.AUC,
        )
        connect(
            self.treeRedacOutline.selectionModel().selectionChanged,
            self.redacMetadata.selectionChanged,
            F.AUC,
        )
        connect(
            self.treeRedacOutline.clicked,
            self.redacMetadata.selectionChanged,
            F.AUC,
        )
        connect(
            self.treeRedacOutline.selectionModel().selectionChanged,
            self.mainEditor.selectionChanged,
            F.AUC,
        )

        # Cheat Sheet
        self.cheatSheet.setModels()

        # Debug
        self.mdlFlatData.setVerticalHeaderLabels(["General info", "Summary"])
        self.tblDebugFlatData.setModel(self.mdlFlatData)
        self.tblDebugPersos.setModel(self.mdlCharacter)
        self.tblDebugPersosInfos.setModel(self.mdlCharacter)
        connect(
            self.tblDebugPersos.selectionModel().currentChanged,
            lambda: self.tblDebugPersosInfos.setRootIndex(
                self.mdlCharacter.index(
                    self.tblDebugPersos.selectionModel().currentIndex().row(),
                    Character.name,
                )
            ),
            F.AUC,
        )

        self.tblDebugPlots.setModel(self.mdlPlots)
        self.tblDebugPlotsPersos.setModel(self.mdlPlots)
        self.tblDebugSubPlots.setModel(self.mdlPlots)
        connect(
            self.tblDebugPlots.selectionModel().currentChanged,
            lambda: self.tblDebugPlotsPersos.setRootIndex(
                self.mdlPlots.index(
                    self.tblDebugPlots.selectionModel().currentIndex().row(),
                    Plot.characters,
                )
            ),
            F.AUC,
        )
        connect(
            self.tblDebugPlots.selectionModel().currentChanged,
            lambda: self.tblDebugSubPlots.setRootIndex(
                self.mdlPlots.index(
                    self.tblDebugPlots.selectionModel().currentIndex().row(),
                    Plot.steps,
                )
            ),
            F.AUC,
        )
        self.treeDebugWorld.setModel(self.mdlWorld)
        self.treeDebugOutline.setModel(self.mdlOutline)
        self.lstDebugLabels.setModel(self.mdlLabels)
        self.lstDebugStatus.setModel(self.mdlStatus)

    def breakConnections(self):
        """Release every signal connection owned by the current project."""
        self.characterController.reset()
        self.plotController.reset()
        self.projectConnections.disconnect_all()

    ###############################################################################
    # HELP
    ###############################################################################

    def centerChildWindow(self, win):
        r = win.geometry()
        r2 = self.geometry()
        win.move(r2.center() - QPoint(int(r.width()/2), int(r.height()/2)))

    def support(self):
        openURL("https://github.com/olivierkes/manuskript/wiki/Technical-Support")

    def locateLogFile(self):
        logfile = getLogFilePath()

        # Make sure we are even logging to a file.
        if not logfile:
            QMessageBox(QMessageBox.Information,
                self.tr("Sorry!"),
                "<p><b>" +
                    self.tr("This session is not being logged.") +
                "</b></p>",
                QMessageBox.Ok).exec()
            return

        # Remind user that log files are at their best once they are complete.
        msg = QMessageBox(QMessageBox.Information,
            self.tr("A log file is a Work in Progress!"),
            "<p><b>" +
                self.tr("The log file \"{}\" will continue to be written to until Manuskript is closed.").format(os.path.basename(logfile)) +
            "</b></p>" +
            "<p>" +
                self.tr("It will now be displayed in your file manager, but is of limited use until you close Manuskript.") +
            "</p>",
            QMessageBox.Ok)

        ret = msg.exec()

        # Open the filemanager.
        if ret == QMessageBox.Ok:
            if not showInFolder(logfile):
                # If everything convenient fails, at least make sure the user can browse to its location manually.
                QMessageBox(QMessageBox.Critical,
                    self.tr("Error!"),
                    "<p><b>" +
                        self.tr("An error was encountered while trying to show the log file below in your file manager.") +
                    "</b></p>" +
                    "<p>" +
                        logfile +
                    "</p>",
                    QMessageBox.Ok).exec()


    def about(self):
        self.dialog = aboutDialog(mw=self)
        self.dialog.setFixedSize(self.dialog.size())
        self.dialog.show()
        # Center about dialog
        self.centerChildWindow(self.dialog)

    ###############################################################################
    # GENERAL AKA UNSORTED
    ###############################################################################

    def wordCount(self, i):

        src = {
            0: self.txtSummarySentence,
            1: self.txtSummaryPara,
            2: self.txtSummaryPage,
            3: self.txtSummaryFull
        }[i]

        lbl = {
            0: self.lblSummaryWCSentence,
            1: self.lblSummaryWCPara,
            2: self.lblSummaryWCPage,
            3: self.lblSummaryWCFull
        }[i]

        wc = wordCount(src.toPlainText())
        if i in [2, 3]:
            pages = self.tr(" (~{} pages)").format(int(wc / 25) / 10.)
        else:
            pages = ""
        lbl.setText(self.tr("Words: {}{}").format(wc, pages))

    def setupMoreUi(self):

        style.styleMainWindow(self)

        # Tool bar on the right
        self.toolbar = collapsibleDockWidgets(Qt.RightDockWidgetArea, self)
        self.toolbar.addCustomWidget(self.tr("Book summary"), self.grpPlotSummary, self.TabPlots, False)
        self.toolbar.addCustomWidget(self.tr("Project tree"), self.treeRedacWidget, self.TabRedac, True)
        self.toolbar.addCustomWidget(self.tr("Metadata"), self.redacMetadata, self.TabRedac, False)
        self.toolbar.addCustomWidget(self.tr("Story line"), self.storylineView, self.TabRedac, False)
        if self._toolbarState:
            self.toolbar.restoreState(self._toolbarState)

        # Hides navigation dock title bar
        self.dckNavigation.setTitleBarWidget(QWidget(None))

        # Custom "tab" bar on the left
        self.lstTabs.setIconSize(QSize(48, 48))
        for i in range(self.tabMain.count()):

            icons = [QIcon.fromTheme("stock_view-details"), #info
                     QIcon.fromTheme("application-text-template"), #applications-publishing
                     F.themeIcon("characters"),
                     F.themeIcon("plots"),
                     F.themeIcon("world"),
                     F.themeIcon("outline"),
                     QIcon.fromTheme("gtk-edit"),
                     QIcon.fromTheme("applications-debugging")
            ]
            self.tabMain.setTabIcon(i, icons[i])

            item = QListWidgetItem(self.tabMain.tabIcon(i),
                                   self.tabMain.tabText(i))
            item.setSizeHint(QSize(item.sizeHint().width(), 64))
            item.setToolTip(self.tabMain.tabText(i))
            item.setTextAlignment(Qt.AlignCenter)
            self.lstTabs.addItem(item)
        self.tabMain.tabBar().hide()
        self.lstTabs.currentRowChanged.connect(self.tabMain.setCurrentIndex)
        self.lstTabs.item(self.TabDebug).setHidden(not self.SHOW_DEBUG_TAB)
        self.tabMain.setTabEnabled(self.TabDebug, self.SHOW_DEBUG_TAB)
        self.tabMain.currentChanged.connect(self.lstTabs.setCurrentRow)

        # Splitters
        self.splitterPersos.setStretchFactor(0, 25)
        self.splitterPersos.setStretchFactor(1, 75)

        self.splitterPlot.setStretchFactor(0, 20)
        self.splitterPlot.setStretchFactor(1, 60)
        self.splitterPlot.setStretchFactor(2, 30)

        self.splitterWorld.setStretchFactor(0, 25)
        self.splitterWorld.setStretchFactor(1, 75)

        self.splitterOutlineH.setStretchFactor(0, 25)
        self.splitterOutlineH.setStretchFactor(1, 75)
        self.splitterOutlineV.setStretchFactor(0, 75)
        self.splitterOutlineV.setStretchFactor(1, 25)

        self.splitterRedacV.setStretchFactor(0, 75)
        self.splitterRedacV.setStretchFactor(1, 25)

        self.splitterRedacH.setStretchFactor(0, 30)
        self.splitterRedacH.setStretchFactor(1, 40)
        self.splitterRedacH.setStretchFactor(2, 30)

        # QFormLayout stretch
        for w in [self.txtWorldDescription, self.txtWorldPassion, self.txtWorldConflict]:
            s = w.sizePolicy()
            s.setVerticalStretch(1)
            w.setSizePolicy(s)

        # Help box
        references = [
            (self.lytTabOverview,
             self.tr("Enter information about your book, and yourself."),
             0),
            (self.lytSituation,
             self.tr(
                     """The basic situation, in the form of a 'What if...?' question. Ex: 'What if the most dangerous
                     evil wizard wasn't able to kill a baby?' (Harry Potter)"""),
             1),
            (self.lytSummary,
             self.tr(
                     """Take time to think about a one sentence (~50 words) summary of your book. Then expand it to
                     a paragraph, then to a page, then to a full summary."""),
             1),
            (self.lytTabPersos,
             self.tr("Create your characters."),
             0),
            (self.lytTabPlot,
             self.tr("Develop plots."),
             0),
            (self.lytTabContext,
             self.tr("Build worlds.  Create hierarchy of broad categories down to specific details."),
             0),
            (self.lytTabOutline,
             self.tr("Create the outline of your masterpiece."),
             0),
            (self.lytTabRedac,
             self.tr("Write."),
             0),
            (self.lytTabDebug,
             self.tr("Debug info. Sometimes useful."),
             0)
        ]

        for widget, text, pos in references:
            label = helpLabel(text, self)
            self.actShowHelp.toggled.connect(label.setVisible, F.AUC)
            widget.layout().insertWidget(pos, label)

        self.actShowHelp.setChecked(False)

        # Spellcheck
        if Spellchecker.isInstalled():
            self.menuDict = QMenu(self.tr("Dictionary"))
            self.menuDictGroup = QActionGroup(self)
            self.updateMenuDict()
            self.menuTools.addMenu(self.menuDict)

            self.actSpellcheck.toggled.connect(self.toggleSpellcheck, F.AUC)
            # self.dictChanged.connect(self.mainEditor.setDict, F.AUC)
            # self.dictChanged.connect(self.redacMetadata.setDict, F.AUC)
            # self.dictChanged.connect(self.outlineItemEditor.setDict, F.AUC)

        else:
            # No Spell check support
            self.actSpellcheck.setVisible(False)
            for lib, requirement in Spellchecker.supportedLibraries().items():
                a = QAction(self.tr("Install {}{} to use spellcheck").format(lib, requirement or ""), self)
                a.setIcon(self.style().standardIcon(QStyle.SP_MessageBoxWarning))
                # Need to bound the lib argument otherwise the lambda uses the same lib value across all calls
                def gen_slot_cb(l):
                    return lambda: self.openSpellcheckWebPage(l)
                a.triggered.connect(gen_slot_cb(lib), F.AUC)
                self.menuTools.addAction(a)


    ###############################################################################
    # SPELLCHECK
    ###############################################################################

    def updateMenuDict(self):

        if not Spellchecker.isInstalled():
            return

        self.menuDict.clear()
        dictionaries = Spellchecker.availableDictionaries()

        # Set first run dictionary
        if self.settingsManager.dict is None:
            self.settingsManager.dict = Spellchecker.getDefaultDictionary()

        # Check if project dict is unavailable on this machine
        dict_available = False
        for lib, dicts in dictionaries.items():
            if dict_available:
                break
            for i in dicts:
                if Spellchecker.normalizeDictName(lib, i) == self.settingsManager.dict:
                    dict_available = True
                    break
        # Reset dict to default one if it's unavailable
        if not dict_available:
            self.settingsManager.dict = Spellchecker.getDefaultDictionary()

        for lib, dicts in dictionaries.items():
            if len(dicts) > 0:
                a = QAction(lib, self)
            else:
                a = QAction(self.tr("{} has no installed dictionaries").format(lib), self)
            a.setEnabled(False)
            self.menuDict.addAction(a)
            for i in dicts:
                a = QAction(i, self)
                a.data = lib
                a.setCheckable(True)
                if Spellchecker.normalizeDictName(lib, i) == self.settingsManager.dict:
                    a.setChecked(True)
                a.triggered.connect(self.setDictionary, F.AUC)
                self.menuDictGroup.addAction(a)
                self.menuDict.addAction(a)
            self.menuDict.addSeparator()

        # If a new dictionary was chosen, apply the change and re-enable spellcheck if it was enabled.
        if not dict_available:
            self.setDictionary()
            self.toggleSpellcheck(self.settingsManager.spellcheck)

        for lib, requirement in Spellchecker.supportedLibraries().items():
            if lib not in dictionaries:
                a = QAction(self.tr("{}{} is not installed").format(lib, requirement or ""), self)
                a.setEnabled(False)
                self.menuDict.addAction(a)
                self.menuDict.addSeparator()

    def setDictionary(self):
        if not Spellchecker.isInstalled():
            return

        for i in self.menuDictGroup.actions():
            if i.isChecked():
                # self.dictChanged.emit(i.text().replace("&", ""))
                self.settingsManager.dict = Spellchecker.normalizeDictName(i.data, i.text().replace("&", ""))

                # Find all textEditView from self, and toggle spellcheck
                for w in self.findChildren(textEditView, QRegExp(".*"),
                                           Qt.FindChildrenRecursively):
                    w.setDict(self.settingsManager.dict)

    def openSpellcheckWebPage(self, lib):
        F.openURL(Spellchecker.getLibraryURL(lib))

    def toggleSpellcheck(self, val):
        self.settingsManager.spellcheck = val

        # Find all textEditView from self, and toggle spellcheck
        for w in self.findChildren(textEditView, QRegExp(".*"),
                                   Qt.FindChildrenRecursively):
            w.toggleSpellcheck(val)

    ###############################################################################
    # SETTINGS
    ###############################################################################

    def settingsLabel(self):
        self.settingsWindow(3)

    def settingsStatus(self):
        self.settingsWindow(4)

    def settingsWindow(self, tab=None):
        self.sw = settingsWindow(self)
        self.sw.hide()
        self.sw.setWindowModality(Qt.ApplicationModal)
        self.sw.setWindowFlags(Qt.Dialog)
        self.centerChildWindow(self.sw)
        if tab:
            self.sw.setTab(tab)
        self.sw.show()

    ###############################################################################
    # TOOLS
    ###############################################################################

    def frequencyAnalyzer(self):
        self.fw = frequencyAnalyzer(self)
        self.fw.show()
        self.centerChildWindow(self.fw)

    def sessionTargets(self):
        self.td = TargetsDialog(self)
        self.td.show()
        self.centerChildWindow(self.td)

    ###############################################################################
    # VIEW MENU
    ###############################################################################

    def generateViewMenu(self):

        values = [
            (self.tr("Nothing"), "Nothing"),
            (self.tr("POV"), "POV"),
            (self.tr("Label"), "Label"),
            (self.tr("Progress"), "Progress"),
            (self.tr("Compile"), "Compile"),
        ]

        menus = [
            (self.tr("Tree"), "Tree", "view-list-tree"),
            (self.tr("Index cards"), "Cork", "view-cards"),
            (self.tr("Outline"), "Outline", "view-outline")
        ]

        submenus = {
            "Tree": [
                (self.tr("Icon color"), "Icon"),
                (self.tr("Text color"), "Text"),
                (self.tr("Background color"), "Background"),
            ],
            "Cork": [
                (self.tr("Icon"), "Icon"),
                (self.tr("Text"), "Text"),
                (self.tr("Background"), "Background"),
                (self.tr("Border"), "Border"),
                (self.tr("Corner"), "Corner"),
            ],
            "Outline": [
                (self.tr("Icon color"), "Icon"),
                (self.tr("Text color"), "Text"),
                (self.tr("Background color"), "Background"),
            ],
        }

        self.menuView.clear()
        self.menuView.addMenu(self.menuMode)
        self.menuView.addSeparator()

        # LOGGER.debug("Generating menus with %s.", self.settingsManager.viewSettings)

        for mnu, mnud, icon in menus:
            m = QMenu(mnu, self.menuView)
            if icon:
                m.setIcon(QIcon.fromTheme(icon))
            for s, sd in submenus[mnud]:
                m2 = QMenu(s, m)
                agp = QActionGroup(m2)
                for v, vd in values:
                    a = QAction(v, m)
                    a.setCheckable(True)
                    a.setData("{},{},{}".format(mnud, sd, vd))
                    if self.settingsManager.viewSettings[mnud][sd] == vd:
                        a.setChecked(True)
                    a.triggered.connect(self.setViewSettingsAction, F.AUC)
                    agp.addAction(a)
                    m2.addAction(a)
                m.addMenu(m2)
            self.menuView.addMenu(m)

    def setViewSettingsAction(self):
        action = self.sender()
        item, part, element = action.data().split(",")
        self.setViewSettings(item, part, element)

    def setViewSettings(self, item, part, element):
        self.settingsManager.viewSettings[item][part] = element
        if item == "Cork":
            self.mainEditor.updateCorkView()
        if item == "Outline":
            self.mainEditor.updateTreeView()
            self.treeOutlineOutline.viewport().update()
        if item == "Tree":
            self.treeRedacOutline.viewport().update()

    ###############################################################################
    # VIEW MODES
    ###############################################################################

    def setViewModeSimple(self):
        self.settingsManager.viewMode = "simple"
        self.tabMain.setCurrentIndex(self.TabRedac)
        self.viewModeFictionVisibilitySwitch(False)
        self.actModeSimple.setChecked(True)

    def setViewModeFiction(self):
        self.settingsManager.viewMode = "fiction"
        self.viewModeFictionVisibilitySwitch(True)
        self.actModeFiction.setChecked(True)

    def viewModeFictionVisibilitySwitch(self, val):
        """
        Switches the visibility of some UI components useful for fiction only
        @param val: sets visibility to val
        """

        # Menu navigation & button in toolbar
        self.toolbar.setDockVisibility(self.dckNavigation, val)

        # POV in metadata
        from manuskript.ui.views.propertiesView import propertiesView
        for w in findWidgetsOfClass(propertiesView):
            w.lblPOV.setVisible(val)
            w.cmbPOV.setVisible(val)

        # POV in outline view
        if val is None and Outline.POV in self.settingsManager.outlineViewColumns:
            self.settingsManager.outlineViewColumns.remove(Outline.POV)

        from manuskript.ui.views.outlineView import outlineView
        for w in findWidgetsOfClass(outlineView):
            w.hideColumns()

        # TODO: clean up all other fiction things in non-fiction view mode
        # Character in search widget
        # POV in settings / views

    ###############################################################################
    # IMPORT / EXPORT
    ###############################################################################

    def doImport(self):
        # Warn about buggy Qt versions and import crash
        #
        # (Py)Qt 5.11 and 5.12 have a bug that can cause crashes when simply
        # setting up various UI elements.
        # This has been reported and verified to happen with File -> Import.
        # See PR #611.
        if re.match("^5\\.1[12](\\.?|$)", qVersion()):
            warning1 = self.tr("PyQt / Qt versions 5.11 and 5.12 are known to cause a crash which might result in a loss of data.")
            warning2 = self.tr("PyQt {} and Qt {} are in use.").format(qVersion(), PYQT_VERSION_STR)

            # Don't translate for debug log.
            LOGGER.warning(warning1)
            LOGGER.warning(warning2)

            msg = QMessageBox(QMessageBox.Warning,
                self.tr("Proceed with import at your own risk"),
                "<p><b>" +
                    warning1 +
                "</b></p>" +
                "<p>" +
                    warning2 +
                "</p>",
                QMessageBox.Abort | QMessageBox.Ignore)
            msg.setDefaultButton(QMessageBox.Abort)

            # Return because user heeds warning
            if msg.exec() == QMessageBox.Abort:
                return

        # Proceed with Import
        self.dialog = importerDialog(mw=self)
        self.dialog.show()
        self.centerChildWindow(self.dialog)


    def doCompile(self):
        self.dialog = exporterDialog(mw=self)
        self.dialog.show()
        self.centerChildWindow(self.dialog)
