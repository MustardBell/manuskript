#!/usr/bin/env python
# --!-- coding: utf8 --!--

import locale
import os

from PyQt5.QtCore import QRegExp, Qt, QDir
from PyQt5.QtGui import QIcon, QBrush, QColor
from PyQt5.QtWidgets import QWidget, QAction, QFileDialog, QSpinBox, QLineEdit, QLabel, QPushButton, QTreeWidgetItem, \
    qApp, QMessageBox

from manuskript.functions import appPath
from manuskript.ui.welcome_ui import Ui_welcome
from manuskript.ui import style as S

import logging
LOGGER = logging.getLogger(__name__)

try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass

class welcome(QWidget, Ui_welcome):
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)

        self.template = []
        self.context = None
        self.btnOpen.clicked.connect(self.openFile)
        self.btnCreate.clicked.connect(self.createFile)
        self.chkLoadLastProject.toggled.connect(self.setAutoLoad)
        self.tree.itemClicked.connect(self.changeTemplate)
        self.btnAddLevel.clicked.connect(self.templateAddLevel)
        self.btnAddWC.clicked.connect(self.templateAddWordCount)
        self.btnCreateText = self.btnCreate.text()

        self.populateTemplates()
        self._templates = self.templates()

    def set_context(self, context):
        self.context = context

    def project_manager(self):
        if self.context is None:
            raise RuntimeError("Welcome context has not been configured.")
        return self.context.project_manager

    def updateValues(self):
        # Auto load
        autoLoad, last = self.getAutoLoadValues()
        self.chkLoadLastProject.setChecked(autoLoad)

        # Recent Files
        self.loadRecents()

    def getLastAccessedDirectory(self):
        lastDirectory = (
            self.context.project_history.last_accessed_directory()
        )
        if lastDirectory != '.':
            LOGGER.info("Last accessed directory \"{}\" loaded.".format(lastDirectory))
        return lastDirectory

    def setLastAccessedDirectory(self, dir):
        self.context.project_history.set_last_accessed_directory(dir)

    ###############################################################################
    # AUTOLOAD
    ###############################################################################

    def showEvent(self, event):
        """Waiting for things to be fully loaded to start opening projects."""
        QWidget.showEvent(self, event)

        # Auto load last project
        autoLoad, last = self.getAutoLoadValues()

        project = self.context.consume_auto_load_project()
        if project:
            self.appendToRecentFiles(project)
            self.project_manager().loadProject(project)

        elif autoLoad and last:
            self.project_manager().loadProject(last)

    def getAutoLoadValues(self):
        """
        Reads manuskript system's settings and returns a tuple:
        - `bool`: whether manuskript should automatically load
                  the last opened project or display the
                  welcome widget.
        - `str`:  the absolute path to the last opened project.
        """
        return self.context.project_history.auto_load_values()

    def setAutoLoad(self, v):
        self.context.project_history.set_auto_load(v)

    ###############################################################################
    # RECENTS
    ###############################################################################

    def loadRecents(self):
        recent_menu = self.context.recent_menu
        recent_menu.setIcon(QIcon.fromTheme("folder-recent"))
        recent_files = self.context.project_history.recent_files()
        if recent_files:
            recent_menu.clear()
            for f in [f for f in recent_files if os.path.exists(f)]:
                name = os.path.split(f)[1]
                a = QAction(name, self)
                a.setData(f)
                a.setStatusTip(f)
                a.triggered.connect(self.loadRecentFile)
                recent_menu.addAction(a)

            self.btnRecent.setMenu(recent_menu)

    def appendToRecentFiles(self, project):
        self.context.project_history.remember_recent_file(project)

    def loadRecentFile(self):
        act = self.sender()
        if not self.project_manager().closeProject():
            return
        self.appendToRecentFiles(act.data())
        self.project_manager().loadProject(act.data())

    ###############################################################################
    # DIALOGS
    ###############################################################################

    def openFile(self):
        lastDirectory = self.getLastAccessedDirectory()

        """File dialog that request an existing file. For opening project."""
        filename = QFileDialog.getOpenFileName(self,
                                               self.tr("Open project"),
                                               lastDirectory,
                                               self.tr("Manuskript project (*.msk);;All files (*)"))[0]
        if filename:
            self.setLastAccessedDirectory(os.path.dirname(filename))
            self.appendToRecentFiles(filename)
            self.project_manager().loadProject(filename)

    def saveAsFile(self):
        lastDirectory = self.getLastAccessedDirectory()

        """File dialog that request a file, existing or not.
        Save data to that file, which then becomes the current project."""
        filename = QFileDialog.getSaveFileName(self,
                                               self.tr("Save project as..."),
                                               lastDirectory,
                                               self.tr("Manuskript project (*.msk)"))[0]

        if filename:
            self.setLastAccessedDirectory(os.path.dirname(filename))
            if filename[-4:] != ".msk":
                filename += ".msk"
            self.appendToRecentFiles(filename)
            # Ensure all file(s) are saved under the new filename.
            self.project_manager().clearSaveCache()
            self.project_manager().saveDatas(filename)
            # Update Window's project name with new filename
            pName = os.path.split(filename)[1]
            if pName.endswith('.msk'):
                pName=pName[:-4]
            self.context.set_window_title(
                pName + " - " + self.tr("Manuskript")
            )

    def createFile(self, filename=None, overwrite=False):
        lastDirectory = self.getLastAccessedDirectory()

        """When starting a new project, ask for a place to save it.
        Datas are not loaded from file, so they must be populated another way."""
        if not filename:
            filename = QFileDialog.getSaveFileName(
                           self,
                           self.tr("Create New Project"),
                           lastDirectory,
                           self.tr("Manuskript project (*.msk)"))[0]

        if filename:
            self.setLastAccessedDirectory(os.path.dirname(filename))
            if filename[-4:] != ".msk":
                filename += ".msk"
            if os.path.exists(filename) and not overwrite:
                # Check if okay to overwrite existing project
                result = QMessageBox.warning(self, self.tr("Warning"),
                    self.tr("Overwrite existing project {} ?").format(filename),
                    QMessageBox.Ok|QMessageBox.Cancel, QMessageBox.Cancel)
                if result == QMessageBox.Cancel:
                    return
            # Create new project
            self.appendToRecentFiles(filename)
            self.loadDefaultDatas()
            self.project_manager().loadProject(
                filename,
                loadFromFile=False,
            )

    ###############################################################################
    # TEMPLATES
    ###############################################################################

    def templates(self):
        return [
            (self.tr("Empty fiction"), [], "Fiction"),
            (self.tr("Novel"), [
                (20, self.tr("Chapter")),
                (5, self.tr("Scene")),
                (500, None)  # A line with None is word count
            ], "Fiction"),
            (self.tr("Novella"), [
                (10, self.tr("Chapter")),
                (5, self.tr("Scene")),
                (500, None)
            ], "Fiction"),
            (self.tr("Short Story"), [
                (10, self.tr("Scene")),
                (1000, None)
            ], "Fiction"),
            (self.tr("Trilogy"), [
                (3, self.tr("Book")),
                (3, self.tr("Section")),
                (10, self.tr("Chapter")),
                (5, self.tr("Scene")),
                (500, None)
            ], "Fiction"),
            (self.tr("Empty non-fiction"), [], "Non-fiction"),
            (self.tr("Research paper"), [
                (3, self.tr("Section")),
                (1000, None)
            ], "Non-fiction")
        ]

    def changeTemplate(self, item, column):
        template = [i for i in self._templates if i[0] == item.text(0)]
        self.btnCreate.setText(self.btnCreateText)

        # Selected item is a template
        if len(template):
            self.template = template[0]
            self.updateTemplate()

        # Selected item is a sample project
        elif item.data(0, Qt.UserRole):
            name = item.data(0, Qt.UserRole)
            # Clear templates
            self.template = self._templates[0]
            self.updateTemplate()
            # Change button text
            self.btnCreate.setText("Open {}".format(name))
            # Load project
            self.project_manager().loadProject(
                appPath(os.path.join("sample-projects", name))
            )

    def updateTemplate(self):
        # Clear layout
        def clearLayout(l):
            while l.count() != 0:
                i = l.takeAt(0)
                if i.widget():
                    i.widget().deleteLater()
                    i.widget().setProperty("templateIndex", None)
                if i.layout():
                    clearLayout(i.layout())

        clearLayout(self.lytTemplate)

        # self.templateLayout.addStretch()
        # l = QGridLayout()
        # self.templateLayout.addLayout(l)

        k = 0
        hasWC = False
        for templateIndex, d in enumerate(self.template[1]):
            spin = QSpinBox(self)
            spin.setRange(0, 999999)
            spin.setValue(d[0])
            # Storing the level of the template in that spinbox, so we can use
            # it to update the template when valueChanged on that spinbox
            # (we do that in self.updateWordCount for convenience).
            spin.setProperty("templateIndex", templateIndex)
            spin.valueChanged.connect(self.updateWordCount)
            if d[1] != None:
                txt = QLineEdit(self)
                txt.setProperty("templateIndex", templateIndex)
                txt.textEdited.connect(self.updateWordCount)
                txt.setText(d[1])

            else:
                hasWC = True
                txt = QLabel(self.tr("words each."), self)

            if k != 0:
                of = QLabel(self.tr("of"), self)
                self.lytTemplate.addWidget(of, k, 0)

                btn = QPushButton("", self)
                btn.setIcon(QIcon.fromTheme("edit-delete"))
                btn.setProperty("deleteRow", k)
                btn.setFlat(True)
                btn.clicked.connect(self.deleteTemplateRow)

                self.lytTemplate.addWidget(btn, k, 3)

            self.lytTemplate.addWidget(spin, k, 1)
            self.lytTemplate.addWidget(txt, k, 2)
            k += 1

        self.btnAddWC.setEnabled(not hasWC and len(self.template[1]) > 0)
        self.btnAddLevel.setEnabled(True)
        self.lblTotal.setVisible(hasWC)
        self.updateWordCount()

    def templateAddLevel(self):
        if len(self.template[1]) > 0 and \
                        self.template[1][len(self.template[1]) - 1][1] == None:
            # has word count, so insert before
            self.template[1].insert(len(self.template[1]) - 1, (10, self.tr("Text")))
        else:
            # No word count, so insert at end
            self.template[1].append((10, self.tr("Something")))
        self.updateTemplate()

    def templateAddWordCount(self):
        self.template[1].append((500, None))
        self.updateTemplate()

    def deleteTemplateRow(self):
        btn = self.sender()
        row = btn.property("deleteRow")
        self.template[1].pop(row)
        self.updateTemplate()

    def updateWordCount(self):
        """
        Updates the word count of the template, and displays it in a label.

        Also, updates self.template, which is used to create the items when
        calling self.createFile.
        """
        # Searching for every spinboxes on the widget, and multiplying
        # their values to get the number of words.
        for s in self.findChildren(QSpinBox, QRegExp(".*"),
                                   Qt.FindChildrenRecursively):
            templateIndex = s.property("templateIndex")
            if (templateIndex is None) or (templateIndex >= len(self.template[1])):
                continue

            # Update self.template to reflect the changed count values
            self.template[1][templateIndex] = (
                s.value(),
                self.template[1][templateIndex][1])

        for t in self.findChildren(QLineEdit, QRegExp(".*"),
                                   Qt.FindChildrenRecursively):
            templateIndex = t.property("templateIndex")
            if (templateIndex is None) or (templateIndex >= len(self.template[1])):
                continue

            # Update self.template to reflect the changed name values
            self.template[1][templateIndex] = (
                self.template[1][templateIndex][0],
                t.text())
        
        total = 0
        for row in self.template[1]:
            try:
                val = int(row[0])
            except ValueError:
                continue

            if total == 0:
                total = val
            else:
                total *= val

        self.lblTotal.setText(self.tr("<b>Total:</b> {} words (~ {} pages)").format(
                locale.format_string("%d", total, grouping=True),
                locale.format_string("%d", total / 250, grouping=True)
        ))

    def addTopLevelItem(self, name):
        item = QTreeWidgetItem(self.tree, [name])
        item.setBackground(0, QBrush(QColor(S.highlightLight)))
        item.setForeground(0, QBrush(QColor(S.highlightedTextDark)))
        item.setTextAlignment(0, Qt.AlignCenter)
        item.setFlags(Qt.ItemIsEnabled)
        f = item.font(0)
        f.setBold(True)
        item.setFont(0, f)
        return item

    def populateTemplates(self):
        self.tree.clear()
        self.tree.setIndentation(0)

        # Add templates
        item = self.addTopLevelItem(self.tr("Fiction"))
        templates = [i for i in self.templates() if i[2] == "Fiction"]
        for t in templates:
            sub = QTreeWidgetItem(item, [t[0]])

        # Add templates: non-fiction
        item = self.addTopLevelItem(self.tr("Non-fiction"))
        templates = [i for i in self.templates() if i[2] == "Non-fiction"]
        for t in templates:
            sub = QTreeWidgetItem(item, [t[0]])


        # Add Demo project
        item = self.addTopLevelItem(self.tr("Demo projects"))
        dir = QDir(appPath("sample-projects"))
        for f in dir.entryList(["*.msk"], filters=QDir.Files):
            sub = QTreeWidgetItem(item, [f[:-4]])
            sub.setData(0, Qt.UserRole, f)

        self.tree.expandAll()

    def loadDefaultDatas(self):
        """Initialize a basic Manuskript project."""
        non_fiction = False
        if self.template:
            selected = [
                value for value in self._templates
                if value[0] == self.template[0]
            ]
            non_fiction = bool(
                selected and selected[0][2] == "Non-fiction"
            )

        self.context.template_initializer.initialize(
            self.template,
            non_fiction=non_fiction,
            labels=[
                (Qt.transparent, ""),
                (Qt.yellow, self.tr("Idea")),
                (Qt.green, self.tr("Note")),
                (Qt.blue, self.tr("Chapter")),
                (Qt.red, self.tr("Scene")),
                (Qt.cyan, self.tr("Research")),
            ],
            statuses=[
                "",
                self.tr("TODO"),
                self.tr("First draft"),
                self.tr("Second draft"),
                self.tr("Final"),
            ],
        )
