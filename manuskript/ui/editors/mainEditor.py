#!/usr/bin/env python
# --!-- coding: utf8 --!--
import locale, os

from PyQt5.QtCore import QModelIndex, QRect, QPoint, pyqtSignal
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QIcon
from PyQt5.QtWidgets import QStackedWidget, QWidget, qApp, QDesktopWidget

from manuskript.enums import Outline
from manuskript.functions import AUC, drawProgress, appPath, uiParse
from manuskript.ui import style
from manuskript.ui.editors.editorWidget import editorWidget
from manuskript.ui.editors.fullscreen_presentation import (
    FullscreenRequest,
    fullscreen_presentation_for,
)
from manuskript.ui.editors.mainEditor_ui import Ui_mainEditor
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationBinding,
    MarkdownPresentationMode,
    presentation_mode_key,
)

try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass

import logging

from manuskript import timing
LOGGER = logging.getLogger(__name__)

class mainEditor(QWidget, Ui_mainEditor):
    """
    `mainEditor` is responsible for opening `outlineItem`s and offering information
    and commands about those `outlineItem`s to the used.

    It contains two main elements:

     1. A `tabSplitter`, which can open any number of `outlineItem`s either in tabs
        (in `QTabWidget`) and/or in split views (children `tabSplitter`s).
     2. An horizontal layout contain a number of buttons and information:

        - Go up button
        - Select folder view: either "text", "cork" or "outline" (see `editorWidget`)
        - Zoom slider for "cork" view
        - Label showing stats about displayed `outlineItem`
        - Fullscreen button

    `mainEditor` is responsible for opening indexes, propagating event to relevant
    views, opening and closing tabs, etc.

    +---------------------------| mainEditor |--------------------------------+
    |                                                                         |
    | +--------| tabSplitter |----------------------------------------------+ |
    | |                               +----------| tabSplitter |---------+  | |
    | |                               |                                  |  | |
    | |  +-----| editorWidget |----+  |  +-------| editorWidget |-----+  |  | |
    | |  |                         |  |  |                            |  |  | |
    | |  +-------------------------+  |  +----------------------------+  |  | |
    | |                               |                                  |  | |
    | |  +-----| editorWidget |----+  |  +-------| editorWidget |-----+  |  | |
    | |  |                         |  |  |                            |  |  | |
    | |  +-------------------------+  |  +----------------------------+  |  | |
    | |                               +----------------------------------+  | |
    | +---------------------------------------------------------------------+ |
    |                                                                         |
    +-------------------------------------------------------------------------+
    | ##  ##  ##  ##                toolbar                            ##  ## |
    +-------------------------------------------------------------------------+
    """

    activeMarkdownPresentationStateChanged = pyqtSignal(object)
    pluginWorkspaceClosed = pyqtSignal()

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)
        self._contentStack = QStackedWidget(self)
        self._contentStack.setObjectName("mainEditorContentStack")
        self.verticalLayout.removeWidget(self.tabSplitter)
        self._contentStack.addWidget(self.tabSplitter)
        self.verticalLayout.insertWidget(0, self._contentStack, 1)
        self._pluginWorkspace = None
        self._focus_source = None
        self._nativeFooterWidgets = (
            self.btnGoUp,
            self.btnRedacFolderText,
            self.btnRedacFolderCork,
            self.btnRedacFolderOutline,
            self.sldCorkSizeFactor,
            self.lblRedacWC,
            self.lblRedacProgress,
            self.cmbMarkdownMode,
            self.btnRedacFullscreen,
        )
        self._updating = False
        self._fullScreen = None

        self.editor_context = None
        self.settings = None
        self._markdownModes = (
            MarkdownPresentationMode.SOURCE,
            MarkdownPresentationMode.FORMATTED_SOURCE,
            MarkdownPresentationMode.LIVE_PREVIEW,
            MarkdownPresentationMode.CLEAN_EDITING,
            MarkdownPresentationMode.READING,
        )
        self._markdownPresentationBinding = MarkdownPresentationBinding(
            set_enabled=self.cmbMarkdownMode.setEnabled,
            state_changed=self._announceMarkdownPresentationState,
            sync_mode=self.syncMarkdownPresentationMode,
            sync_allowed_modes=self.syncMarkdownPresentationModes,
        )
        self.cmbMarkdownMode.setEnabled(False)

        # Connections --------------------------------------------------------

        self.btnGoUp.clicked.connect(self.goToParentItem)
        self.sldCorkSizeFactor.valueChanged.connect(
                self.setCorkSizeFactor, AUC)
        self.btnRedacFolderCork.toggled.connect(
                self.sldCorkSizeFactor.setVisible, AUC
        )
        self.btnRedacFolderText.clicked.connect(
                lambda v: self.setFolderView("text"), AUC)
        self.btnRedacFolderCork.clicked.connect(
                lambda v: self.setFolderView("cork"), AUC)
        self.btnRedacFolderOutline.clicked.connect(
                lambda v: self.setFolderView("outline"), AUC)

        self.btnRedacFullscreen.clicked.connect(
                self.showFullScreen, AUC)
        self.cmbMarkdownMode.currentIndexChanged.connect(
            self.setMarkdownPresentationMode,
            AUC,
        )

        # self.tab.setDocumentMode(False)

        # Bug in Qt < 5.5: doesn't always load icons from custom theme.
        # Cf. https://github.com/qtproject/qtbase/commit/a8621a3f85e64f1252a80ae81a6e22554f7b3f44
        # Since those are important, we provide fallback.
        self.btnRedacFolderCork.setIcon(QIcon.fromTheme("view-cards",
                                        QIcon(appPath(os.path.join("icons", "NumixMsk", "256x256", "actions", "view-cards.svg")))))
        self.btnRedacFolderOutline.setIcon(QIcon.fromTheme("view-outline",
                                           QIcon(appPath(os.path.join("icons", "NumixMsk", "256x256", "actions", "view-outline.svg")))))
        self.btnRedacFolderText.setIcon(QIcon.fromTheme("view-text",
                                        QIcon(appPath(os.path.join("icons", "NumixMsk", "256x256", "actions", "view-text.svg")))))

        for btn in [self.btnRedacFolderCork, self.btnRedacFolderText, self.btnRedacFolderOutline]:
            btn.setToolTip(btn.text())
            btn.setText("")

    def set_focus_source(self, focus_source):
        self._focus_source = focus_source
        self.tabSplitter.set_focus_source(focus_source)

    def set_context(self, context):
        self.editor_context = context
        if context.text_editor is not None:
            self.settings = context.text_editor.settings
        self.tabSplitter.set_context(context)
        self.attachMarkdownPresentationState(
            self._currentMarkdownPresentationState()
        )

    def clear_context(self):
        self.closePluginWorkspace()
        self.attachMarkdownPresentationState(None)
        self.tabSplitter.set_context(None)
        self.editor_context = None

    def attachMarkdownPresentationState(self, state):
        self._markdownPresentationBinding.attach(state)

    def _announceMarkdownPresentationState(self, state):
        self.activeMarkdownPresentationStateChanged.emit(state)

    def _currentMarkdownPresentationState(self):
        editor = self.currentEditor()
        return (
            getattr(editor, "markdownPresentation", None)
            if editor is not None
            else None
        )

    def setMarkdownPresentationMode(self, index):
        if not 0 <= index < len(self._markdownModes):
            return
        self._markdownPresentationBinding.set_mode(
            self._markdownModes[index]
        )

    def syncMarkdownPresentationMode(self, mode):
        mode = presentation_mode_key(mode)
        try:
            index = self._markdownModes.index(mode)
        except ValueError:
            return
        previous = self.cmbMarkdownMode.blockSignals(True)
        self.cmbMarkdownMode.setCurrentIndex(index)
        self.cmbMarkdownMode.blockSignals(previous)

    def syncMarkdownPresentationModes(self, modes):
        modes = tuple(presentation_mode_key(mode) for mode in modes)
        state = self._markdownPresentationBinding.state
        previous = self.cmbMarkdownMode.blockSignals(True)
        self.cmbMarkdownMode.clear()
        self._markdownModes = modes
        for mode in modes:
            self.cmbMarkdownMode.addItem(
                state.label_for(mode)
                if state is not None else str(getattr(mode, "value", mode))
            )
        self.cmbMarkdownMode.blockSignals(previous)
        if state is not None:
            self.syncMarkdownPresentationMode(state.mode)

    ###############################################################################
    # TABS
    ###############################################################################

    def currentTabWidget(self):
        """The tab area the person is working in.

        Found by asking which area actually holds the focused widget,
        which works whatever shape the editor is in. Following the chain
        of neighbours could only describe a comb, and reported a divided
        half as though it held documents.
        """
        ts = self.tabSplitter
        while ts is not None:
            if ts.focusTab != 1 and ts.secondTab is not None:
                ts = ts.secondTab
                continue
            if ts.firstTab is not None:
                # Its own half is divided, so the answer is in there.
                ts = ts.firstTab
                continue
            return ts.tab
        # No area claims focus, which should not happen; the first one is
        # where a single-area editor always is.
        leaves = self.allTabSplitters()
        return leaves[0].tab if leaves else self.tabSplitter.tab

    def currentEditor(self, tabWidget=None):
        if tabWidget == None:
            tabWidget = self.currentTabWidget()
        return tabWidget.currentWidget()

    def tabChanged(self, index=QModelIndex()):
        self.attachMarkdownPresentationState(
            self._currentMarkdownPresentationState()
        )
        if self.currentEditor():
            index = self.currentEditor().currentIndex
            view = self.currentEditor().folderView
            self.updateFolderViewButtons(view)
        else:
            index = QModelIndex()

        self.updateMainTreeView(index)

        self.updateStats()
        self.updateThingsVisible(index)

    def updateMainTreeView(self, index):
        if not index.isValid() or self.editor_context is None:
            return

        self._updating = True
        self.editor_context.outline_tree.setCurrentIndex(index)
        self._updating = False

    def closeAllTabs(self):
        for ts in self.allTabSplitters():
            while(ts.tab.count()):
                ts.closeTab(0)

        for ts in reversed(self.allTabSplitters()):
            ts.closeSplit()

    def close(self):
        if self._fullScreen is not None:
            self._fullScreen.leaveFullscreen()

    def allTabs(self, tabWidget=None):
        """Returns all the tabs from the given tabWidget. If tabWidget is None, from the current tabWidget."""
        if tabWidget == None:
            tabWidget = self.currentTabWidget()
        return [tabWidget.widget(i) for i in range(tabWidget.count())]

    def allAllTabs(self):
        """Returns a list of all tabs, from all tabWidgets."""
        r = []
        for ts in self.allTabSplitters():
            r.extend(self.allTabs(ts.tab))
        return r

    def allTabSplitters(self):
        """Every area that holds documents, in the order they appear.

        A walk of the tree rather than of a chain: an area whose own half
        has been divided holds no documents itself, and the areas inside
        that half would be missed entirely by following neighbours.
        """
        return self.tabSplitter.leaves()

    ###############################################################################
    # SELECTION AND UPDATES
    ###############################################################################

    def selectionChanged(self):
        if self._updating:
            return

        # This might be called during a drag n drop operation, or while deleting
        # items. If so, we don't want to do anything.
        if self.editor_context is None:
            return
        outline_model = self.editor_context.outline_model
        outline_tree = self.editor_context.outline_tree
        if not outline_model._removingRows:
            if len(outline_tree.selectionModel().
                selection().indexes()) == 0:
                idx = QModelIndex()
            else:
                idx = outline_tree.currentIndex()

            self.setCurrentModelIndex(idx)
            self.updateThingsVisible(idx)

    def openIndexes(self, indexes, newTab=False):
        for i in indexes:
            self.setCurrentModelIndex(i, newTab)

    def goToParentItem(self):
        if self.currentEditor() and self.editor_context is not None:
            idx = self.currentEditor().currentIndex
            self.editor_context.outline_tree.setCurrentIndex(idx.parent())

    def setCurrentModelIndex(self, index, newTab=False, tabWidget=None):
        if self.editor_context is None:
            return

        if self.pluginWorkspaceActive:
            # A workspace replaces the editor rather than sitting over it,
            # so there is nothing here to open a document into -- and
            # opening one would take the project's buffer back from the
            # workspace pane that is showing it. The selection is followed
            # again when the workspace closes.
            return

        title = self.getIndexTitle(index)
        # Opening a document is a blocking milestone of its own: reopening
        # the tabs a session left behind is most of what applying settings
        # costs, and it is one span per document that answers why.
        with timing.span("editor.open_document"):
            return self._openDocument(index, newTab, tabWidget, title)

    def _openDocument(self, index, newTab, tabWidget, title):

        if tabWidget == None:
            # no tabWidget specified, update all tabs of views that are a target
            for ts in self.allTabSplitters():
                if ts.isTarget:
                    self.setCurrentModelIndex(index, newTab, tabWidget=ts.tab)
            # additionally always update the current tabWidget
            tabWidget = self.currentTabWidget()

        # Checking if tab is already opened
        for w in self.allTabs(tabWidget):
            if w.currentIndex == index:
                tabWidget.setCurrentWidget(w)
                return

        if qApp.keyboardModifiers() & Qt.ControlModifier:
            newTab = True

        if newTab or not tabWidget.count():
            editor = editorWidget(
                self,
                self.editor_context,
                focus_source=self._focus_source,
            )
            editor.setCurrentModelIndex(index)
            editor._tabWidget = tabWidget
            i = tabWidget.addTab(editor, editor.ellidedTitle(title))
            tabWidget.setTabToolTip(i, title)
            tabWidget.setCurrentIndex(tabWidget.count() - 1)
        else:
            self.currentEditor(tabWidget).setCurrentModelIndex(index)
            #tabWidget.setTabText(tabWidget.currentIndex(), title)

    def updateTargets(self):
        """Updates all tabSplitter that are targets. This is called from editorWidget."""
        index = self.sender().currentIndex()

        for ts in self.allTabSplitters():
            if ts.isTarget:
                self.updateMainTreeView(index)
                self.setCurrentModelIndex(index, tabWidget=ts.tab)
                self.updateThingsVisible(index)

    def getIndexTitle(self, index):
        if not index.isValid():
            title = self.tr("Root")
        else:
            title = index.internalPointer().title()

        return title

    ###############################################################################
    # DOCUMENT COMMAND ROUTING
    ###############################################################################

    def document_command_target(self, _command):
        return None if self.pluginWorkspaceActive else self.currentEditor()

    @property
    def pluginWorkspaceActive(self):
        return self._pluginWorkspace is not None

    def showPluginWorkspace(self, widget):
        if widget is self._pluginWorkspace:
            return
        self.closePluginWorkspace()
        self._pluginWorkspace = widget
        self._contentStack.addWidget(widget)
        self._contentStack.setCurrentWidget(widget)
        for control in self._nativeFooterWidgets:
            control.hide()
        self.attachMarkdownPresentationState(None)
        self._standTabsDown()
        widget.setFocus(Qt.OtherFocusReason)

    def closePluginWorkspace(self):
        workspace = self._pluginWorkspace
        if workspace is None:
            return
        self._pluginWorkspace = None
        self._contentStack.setCurrentWidget(self.tabSplitter)
        self._contentStack.removeWidget(workspace)
        for control in self._nativeFooterWidgets:
            control.show()
        self._resumeTabs()
        self.tabChanged()
        # The outline was still selectable while the workspace stood in for
        # the editor, so what is selected now is what the reader last asked
        # for -- not what the tabs were showing before it opened.
        self.selectionChanged()
        self.pluginWorkspaceClosed.emit()

    def _standTabsDown(self):
        """Let hidden tabs release their documents and formatting work.

        Visible views now have independent projection documents, so a hidden
        tab can no longer impose its wrap width on a workspace pane. Standing
        down remains worthwhile because an invisible editor need not keep a
        layout and highlighter alive.
        """
        for tab in self.allAllTabs():
            stand_down = getattr(tab, "standDown", None)
            if callable(stand_down):
                stand_down()

    def _resumeTabs(self):
        for tab in self.allAllTabs():
            resume = getattr(tab, "resume", None)
            if callable(resume):
                resume()

    ###############################################################################
    # UI
    ###############################################################################

    def updateThingsVisible(self, index):
        if index.isValid():
            visible = index.internalPointer().isFolder()
        else:
            visible = True

        self.btnRedacFolderText.setVisible(visible)
        self.btnRedacFolderCork.setVisible(visible)
        self.btnRedacFolderOutline.setVisible(visible)
        self.sldCorkSizeFactor.setVisible(visible and self.btnRedacFolderCork.isChecked())
        self.btnRedacFullscreen.setVisible(not visible)

    def updateFolderViewButtons(self, view):
        if view == "text":
            self.btnRedacFolderText.setChecked(True)
        elif view == "cork":
            self.btnRedacFolderCork.setChecked(True)
        elif view == "outline":
            self.btnRedacFolderOutline.setChecked(True)

    def updateStats(self):

        if not self.currentEditor() or self.editor_context is None:
            return

        index = self.currentEditor().currentIndex
        
        if index.isValid():
            item = index.internalPointer()
        else:
            item = self.editor_context.outline_model.rootItem

        if not item:
            item = self.editor_context.outline_model.rootItem

        cc = item.data(Outline.charCount)
        wc = item.data(Outline.wordCount)
        goal = item.data(Outline.goal)
        chars = item.data(Outline.charCount) # len(item.data(Outline.text)) 
        progress = item.data(Outline.goalPercentage)

        goal = uiParse(goal, None, int, lambda x: x>=0)
        progress = uiParse(progress, 0.0, float)

        if not cc:
            cc = 0
        
        if not wc:
            wc = 0

        if goal:
            self.lblRedacProgress.show()
            rect = self.lblRedacProgress.geometry()
            rect = QRect(QPoint(0, 0), rect.size())
            self.px = QPixmap(rect.size())
            self.px.fill(Qt.transparent)
            p = QPainter(self.px)
            drawProgress(p, rect, progress, 2)
            del p
            self.lblRedacProgress.setPixmap(self.px)

            if self.settings.progressChars:
                self.lblRedacWC.setText(self.tr("({} chars) {}  words / {} ").format(
                        locale.format_string("%d", cc, grouping=True),
                        locale.format_string("%d", wc, grouping=True),
                        locale.format_string("%d", goal, grouping=True)))
                self.lblRedacWC.setToolTip("")
            else:
                self.lblRedacWC.setText(self.tr("{}  words / {} ").format(
                        locale.format_string("%d", wc, grouping=True),
                        locale.format_string("%d", goal, grouping=True)))
                self.lblRedacWC.setToolTip(self.tr("{} chars").format(
                        locale.format_string("%d", cc, grouping=True)))
        else:
            self.lblRedacProgress.hide()

            if self.settings.progressChars:
                self.lblRedacWC.setText(self.tr("{} chars ").format(
                        locale.format_string("%d", cc, grouping=True)))
                self.lblRedacWC.setToolTip("")
            else:
                self.lblRedacWC.setText(self.tr("{} words ").format(
                        locale.format_string("%d", wc, grouping=True)))
                self.lblRedacWC.setToolTip(self.tr("{} chars").format(
                        locale.format_string("%d", cc, grouping=True)))

    ###############################################################################
    # VIEWS
    ###############################################################################

    def setFolderView(self, view):
        if self.currentEditor():
            self.currentEditor().setFolderView(view)

    def setCorkSizeFactor(self, val):
        for w in self.allAllTabs():
            w.setCorkSizeFactor(val)
        self.settings.corkSizeFactor = val

    def updateCorkView(self):
        # Re-resolve the style rather than only repainting: this is the
        # entry point used after cork settings change, and the chosen card
        # style is one of them.
        for w in self.allAllTabs():
            w.corkView.updateCardStyle()

    def updateCorkBackground(self):
        for w in self.allAllTabs():
            w.corkView.updateBackground()

    def updateTreeView(self):
        for w in self.allAllTabs():
            w.outlineView.viewport().update()

    def showFullScreen(self):
        """Ask the mode on screen to take the screen.

        This control is a state switch. Which modes can be shown full size,
        and how, is the modes' business: deciding it here meant a mode the
        button had not been told about was shown the wrong surface, or none.
        """

        editor = self.currentEditor()
        if not editor:
            return
        mode = editor.markdownPresentation.mode
        request = FullscreenRequest(
            index=editor.currentIndex,
            settings=self.settings,
            widget=editor,
            text_editor_context=self.editor_context.text_editor,
            markup_profile=editor.markupProfile,
            screen_number=QDesktopWidget().screenNumber(widget=self),
        )
        self._fullScreen = fullscreen_presentation_for(mode).enter(request)
        if self._fullScreen is None:
            return
        # Clean the variable when closing fullscreen prevent errors
        self._fullScreen.exited.connect(self.clearFullScreen)

    def clearFullScreen(self):
        self._fullScreen = None

    ###############################################################################
    # DICT AND STUFF LIKE THAT
    ###############################################################################

    def setDict(self, dict):
        for w in self.allAllTabs():
            w.setDict(dict)

    def toggleSpellcheck(self, val):
        for w in self.allAllTabs():
            w.toggleSpellcheck(val)
