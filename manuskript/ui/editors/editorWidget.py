#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import pyqtSignal, QModelIndex
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QWidget, QFrame, QSpacerItem, QSizePolicy
from PyQt5.QtWidgets import QVBoxLayout, qApp, QStyle

from manuskript.commands import DocumentCommand
from manuskript.functions import AUC
from manuskript.ui.editors.editorWidget_ui import Ui_editorWidget_ui
from manuskript.ui.editors.editorOverlayButton import (
    OVERLAY_HEIGHT,
    OVERLAY_MARGIN,
)
from manuskript.ui.editors.editorTextHistory import (
    EditorTextHistory,
)
from manuskript.ui.editors.historyToolButtons import (
    HistoryToolButton,
)
from manuskript.ui.editors.markdownModeToolButton import (
    MarkdownModeToolButton,
)
from manuskript.ui.editors.markupProfileToolButton import (
    MarkupProfileToolButton,
)
from manuskript.ui.editors.markdownEditorHost import MarkdownEditorHost
from manuskript.ui.views.MDEditView import MDEditView
from manuskript.ui.tools.splitDialog import open_split_dialog
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationDefaults,
    MarkdownPresentationMode,
    MarkdownPresentationState,
)


class editorWidget(QWidget, Ui_editorWidget_ui):
    """
    `editorWidget` is a class responsible for displaying and editing one
    `outlineItem`. This item can be a folder or a text.

    It has four views (see `self.setView`)

      - For folders: "text", "outline" or "cork" (set in `self.folderView`)

        Text: displays a list of `textEditView` in a scroll area

        Outline: displays an outline, using an `outlineView`

        Cork: displays flash cards, using a `corkView`

      - For text: item is simply displayed in a `textEditView`

    All those views are contained in `editorWidget` single widget: `self.stack`.

    `editorWidget` are managed in `tabSplitted` (that allow to open several
    `outlineItem`s, either in Tabs or in split views.

    `tabSplitted` are in turn managed by the `mainEditor`, which is unique and
    gives UI buttons to manage all those views.
    """

    toggledSpellcheck = pyqtSignal(bool)
    dictChanged = pyqtSignal(str)

    _maxTabTitleLength = 24

    def __init__(self, parent, editor_context=None):
        QWidget.__init__(self, parent)
        self.setupUi(self)
        self.horizontalLayout_2.removeWidget(self.txtRedacText)
        self.markdownEditorHost = MarkdownEditorHost(
            self.txtRedacText,
            self.text,
        )
        self.horizontalLayout_2.addWidget(self.markdownEditorHost)
        self.main_editor = (
            parent if hasattr(parent, "updateTargets") else None
        )
        self.settings = self.txtRedacText.settings
        self.editor_context = None
        self.outline_context = None
        if editor_context is not None:
            self.set_context(editor_context)
        self.markdownPresentation = MarkdownPresentationState(
            MarkdownPresentationDefaults.load(self.settings),
            parent=self,
        )
        self.txtRedacText.setPresentationState(
            self.markdownPresentation
        )
        self.markdownModeButton = MarkdownModeToolButton(
            self.markdownPresentation,
            self,
        )
        self.markdownModeButton.resize(38, OVERLAY_HEIGHT)
        self.textHistory = EditorTextHistory(self, parent=self)
        self.undoButton = HistoryToolButton(self.textHistory, False, self)
        self.redoButton = HistoryToolButton(self.textHistory, True, self)
        for button in (self.undoButton, self.redoButton):
            button.resize(32, OVERLAY_HEIGHT)
        self.pageType = None
        markup_profiles = (
            self.editor_context.text_editor.markup_profiles
            if self.editor_context is not None
            and self.editor_context.text_editor is not None
            else None
        )
        self.markupProfile = (
            markup_profiles.create_state(parent=self)
            if markup_profiles is not None
            else None
        )
        self.markupProfileButton = (
            MarkupProfileToolButton(self.markupProfile, self)
            if self.markupProfile is not None
            else None
        )
        if self.markupProfileButton is not None:
            self.markupProfileButton.resize(38, OVERLAY_HEIGHT)
            self.markupProfile.changed.connect(
                self._markupProfileChanged
            )
            self.txtRedacText.setMarkupProfileState(
                self.markupProfile
            )
            self._markupProfileChanged()
        page_types = (
            self.editor_context.text_editor.page_types
            if self.editor_context is not None
            and self.editor_context.text_editor is not None
            else None
        )
        self.pageType = (
            page_types.create_state(parent=self)
            if page_types is not None
            else None
        )
        if self.pageType is not None:
            self.pageType.changed.connect(self._pageTypeChanged)
            self.txtRedacText.setPageTypeState(self.pageType)
        self._positionMarkdownModeButton()
        self.markdownModeButton.raise_()
        self.undoButton.raise_()
        self.redoButton.raise_()
        if self.markupProfileButton is not None:
            self.markupProfileButton.raise_()
        self.currentIndex = QModelIndex()
        self.currentID = None
        self.txtEdits = []
        self.markdownEditorHosts = []
        self.pageTypeStates = []
        self.scroll.setBackgroundRole(QPalette.Base)
        self.toggledSpellcheck.connect(self.txtRedacText.toggleSpellcheck, AUC)
        self.dictChanged.connect(self.txtRedacText.setDict, AUC)
        self.txtRedacText.setHighlighting(True)
        self.currentDict = ""
        self.spellcheck = self.settings.spellcheck
        self.folderView = "cork"
        self._tabWidget = None  # set by mainEditor on creation

        self._model = None

        # Capture textEdit scrollbar, so that we can put it outside the margins.
        self.txtEditScrollBar = self.txtRedacText.verticalScrollBar()
        self.txtEditScrollBar.setParent(self)
        self.stack.currentChanged.connect(self.setScrollBarVisibility)
        self.txtRedacText.presentationModeChanged.connect(
            self.setScrollBarVisibility
        )

        # def setModel(self, model):
        # self._model = model
        # self.setView()

    def set_context(self, editor_context):
        self.editor_context = editor_context
        self.outline_context = editor_context.outline_views
        if editor_context.text_editor is not None:
            self.settings = editor_context.text_editor.settings
            self.txtRedacText.set_text_editor_context(
                editor_context.text_editor
            )
            for editor in getattr(self, "txtEdits", []):
                editor.set_text_editor_context(editor_context.text_editor)
        self.corkView.set_outline_context(self.outline_context)
        self.outlineView.set_outline_context(self.outline_context)

    def resizeEvent(self, event):
        """
        textEdit's scrollBar has been reparented to self. So we need to
        update it's geometry when self is resized, and put it where we want it
        to be.
        """
        # Update scrollbar geometry
        r = self.geometry()
        w = 10  # Cf. style.mainEditorTabSS
        r.setWidth(w)
        r.moveRight(self.geometry().width())
        self.txtEditScrollBar.setGeometry(r)
        self._positionMarkdownModeButton()
        self.markdownModeButton.raise_()
        self.undoButton.raise_()
        self.redoButton.raise_()
        if self.markupProfileButton is not None:
            self.markupProfileButton.raise_()

        QWidget.resizeEvent(self, event)

    def _positionMarkdownModeButton(self):
        self.markdownModeButton.move(
            max(0, self.width() - self.markdownModeButton.width() - 12),
            OVERLAY_MARGIN,
        )
        if self.markupProfileButton is not None:
            self.markupProfileButton.move(
                max(
                    0,
                    self.markdownModeButton.x()
                    - self.markupProfileButton.width()
                    - 4,
                ),
                OVERLAY_MARGIN,
            )
        self.undoButton.move(12, OVERLAY_MARGIN)
        self.redoButton.move(
            self.undoButton.x() + self.undoButton.width() + 4,
            OVERLAY_MARGIN,
        )
        self._reserveOverlaySpace()

    def _reserveOverlaySpace(self):
        """Keep the document clear of the buttons floating over it.

        The buttons are children of this widget rather than of a toolbar,
        so without a reserved strip the first line of the scene scrolls
        underneath them. The strip goes on the layout holding the whole
        stack rather than on individual editors: switching to Reading or
        to a page wizard swaps in a sibling view, and margins applied per
        editor would vanish with it.
        """
        # isVisibleTo, not isVisible: the latter is false while the window
        # is still hidden, which would drop the strip during construction.
        reserved = (
            OVERLAY_MARGIN * 2 + OVERLAY_HEIGHT
            if self.markdownModeButton.isVisibleTo(self)
            else 0
        )
        self.verticalLayout_2.setContentsMargins(0, reserved, 0, 0)

    def _markupProfileChanged(self):
        self._refreshPresentationModes()
        for editor in [self.txtRedacText] + list(
            getattr(self, "txtEdits", [])
        ):
            if not getattr(editor, "_contentReadOnly", False):
                editor.setMarkupProfileState(self.markupProfile)

    def _pageTypeChanged(self):
        self._refreshPresentationModes()

    def _refreshPresentationModes(self):
        page_modes = (
            self.pageType.allowed_presentation_modes
            if self.pageType is not None
            else None
        )
        modes = (
            page_modes
            if page_modes is not None
            else tuple(MarkdownPresentationMode)
            if self.markupProfile is None
            else self.markupProfile.allowed_presentation_modes
        )
        self.markdownPresentation.set_allowed_modes(modes)

    def setScrollBarVisibility(self, *_args):
        """
        Since the texteEdit scrollBar has been reparented to self, it is not
        hidden when stack changes. We have to do it manually.
        """
        source_editor_visible = (
            self.stack.currentIndex() == 0
            and self.txtRedacText.presentationMode
            not in (
                MarkdownPresentationMode.LIVE_PREVIEW,
                MarkdownPresentationMode.READING,
            )
        )
        self.txtEditScrollBar.setVisible(source_editor_visible)

    def setFolderView(self, v):
        oldV = self.folderView
        if v == "cork":
            self.folderView = "cork"
        elif v == "outline":
            self.folderView = "outline"
        else:
            self.folderView = "text"

        # Saving value
        self.settings.folderView = self.folderView

        if oldV != self.folderView and self.currentIndex:
            self.setCurrentModelIndex(self.currentIndex)

        self._updateMarkdownModeButtonVisibility()

    def _updateMarkdownModeButtonVisibility(self):
        visible = self.stack.currentIndex() in (0, 1)
        self.markdownModeButton.setVisible(visible)
        for button in (self.undoButton, self.redoButton):
            button.setVisible(visible)
        if self.markupProfileButton is not None:
            service = self.markupProfile.service
            has_profiles = bool(
                service.replacements() or service.augmentations()
            )
            self.markupProfileButton.setVisible(
                visible and has_profiles
            )
        self._reserveOverlaySpace()

    def setCorkSizeFactor(self, v):
        self.corkView.itemDelegate().setCorkSizeFactor(v)
        self.redrawCorkItems()

    def redrawCorkItems(self):
        r = self.corkView.rootIndex()

        if r.isValid():
            count = r.internalPointer().childCount()
        elif self._model:
            count = self._model.rootItem.childCount()
        else:
            count = 0

        for c in range(count):
            self.corkView.itemDelegate().sizeHintChanged.emit(r.child(c, 0))

    def updateTabTitle(self):
        """
        `editorWidget` belongs to a `QTabWidget` in a `tabSplitter`. We update
        the tab title to reflect that of current item.
        """
        # `self._tabWidget` is set by mainEditor when creating tab and `editorWidget`.
        # if `editorWidget` is ever used out of `mainEditor`, this could throw
        # an error.
        if not self._tabWidget:
            return

        if self.currentIndex.isValid():
            item = self.currentIndex.internalPointer()
        elif self._model:
            item = self._model.rootItem
        else:
            return

        i = self._tabWidget.indexOf(self)

        self._tabWidget.setTabText(i, self.ellidedTitle(item.title()))
        self._tabWidget.setTabToolTip(i, item.title())

    def ellidedTitle(self, title):
        if len(title) > self._maxTabTitleLength:
            return "{}…".format(title[:self._maxTabTitleLength])
        else:
            return title

    def setView(self):
        # Counting the number of other selected items
        # sel = []
        # for i in the main outline tree selection:
        # if i.column() != 0: continue
        # if i not in sel: sel.append(i)

        # if len(sel) != 0:
        # item = index.internalPointer()
        # else:
        # index = QModelIndex()
        # item = self.editor_context.outline_model.rootItem

        # self.currentIndex = index

        if self.currentIndex.isValid():
            item = self.currentIndex.internalPointer()
        else:
            item = (
                self.editor_context.outline_model.rootItem
                if self.editor_context is not None
                else self._model.rootItem
            )

        self.updateTabTitle()

        def addTitle(itm):
            edt = MDEditView(self, html="<h{l}>{t}</h{l}>".format(l=min(itm.level() + 1, 5), t=itm.title()),
                               autoResize=True, settings=self.settings)
            if self.editor_context.text_editor is not None:
                edt.set_text_editor_context(
                    self.editor_context.text_editor
                )
            edt.setFrameShape(QFrame.NoFrame)
            self.txtEdits.append(edt)
            l.addWidget(edt)

        def addLine():
            line = QFrame(self.text)
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            l.addWidget(line)

        def addText(itm):
            edt = MDEditView(self,
                               index=itm.index(),
                               spellcheck=self.spellcheck,
                               dict=self.settings.dict,
                               highlighting=True,
                               autoResize=True,
                               settings=self.settings)
            host = MarkdownEditorHost(edt, self)
            edt.setPresentationState(self.markdownPresentation)
            if self.markupProfile is not None:
                edt.setMarkupProfileState(self.markupProfile)
            if (
                self.editor_context.text_editor is not None
                and self.editor_context.text_editor.page_types is not None
            ):
                page_type = (
                    self.editor_context.text_editor.page_types.create_state(
                        item=itm,
                        parent=edt,
                    )
                )
                self.pageTypeStates.append(page_type)
                edt.setPageTypeState(page_type)
            if self.editor_context.text_editor is not None:
                edt.set_text_editor_context(
                    self.editor_context.text_editor
                )
            edt.setFrameShape(QFrame.NoFrame)
            edt.setStatusTip("{}".format(itm.path()))
            self.toggledSpellcheck.connect(edt.toggleSpellcheck, AUC)
            self.dictChanged.connect(edt.setDict, AUC)
            # edt.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            self.txtEdits.append(edt)
            self.markdownEditorHosts.append(host)
            l.addWidget(host)

        def addChildren(itm):
            for c in range(itm.childCount()):
                child = itm.child(c)

                if child.isFolder():
                    addTitle(child)
                    addChildren(child)

                else:
                    addText(child)
                    addLine()

        def addSpacer():
            l.addItem(QSpacerItem(10, 1000, QSizePolicy.Minimum, QSizePolicy.Expanding))

            # Display multiple selected items
            # if len(sel) > 1 and False:  # Buggy and not very useful, skip
            # self.stack.setCurrentIndex(1)
            # w = QWidget()
            # l = QVBoxLayout(w)
            # self.txtEdits = []
            # for idx in sel:
            # sItem = idx.internalPointer()
            # addTitle(sItem)
            # if sItem.isFolder():
            # addChildren(sItem)
            # else:
            # addText(sItem)
            # addLine()
            # addSpacer()
            # self.scroll.setWidget(w)

        if item and item.isFolder() and self.folderView == "text":
            self.stack.setCurrentIndex(1)
            w = QWidget()
            w.setObjectName("editorWidgetFolderText")
            l = QVBoxLayout(w)
            opt = self.settings.textEditor
            background = (opt["background"] if not opt["backgroundTransparent"]
                          else "transparent")
            w.setStyleSheet("background: {};".format(background))
            self.stack.widget(1).setStyleSheet("background: {}"
                                               .format(background))
            # self.scroll.setWidgetResizable(False)

            self.txtEdits = []
            self.markdownEditorHosts = []
            self.pageTypeStates = []

            if item != self._model.rootItem:
                addTitle(item)

            addChildren(item)
            addSpacer()
            self.scroll.setWidget(w)

        elif item and item.isFolder() and self.folderView == "cork":
            self.stack.setCurrentIndex(2)
            self.corkView.setModel(self._model)
            self.corkView.setRootIndex(self.currentIndex)
            try:
                selection_changed = self.outline_context.selection_changed
                if selection_changed is not None:
                    self.corkView.selectionModel().selectionChanged.connect(
                        selection_changed,
                        AUC,
                    )
                    self.corkView.clicked.connect(
                        selection_changed,
                        AUC,
                    )
                if self.main_editor is not None:
                    self.corkView.clicked.connect(
                        self.main_editor.updateTargets,
                        AUC,
                    )
            except TypeError:
                pass

        elif item and item.isFolder() and self.folderView == "outline":
            self.stack.setCurrentIndex(3)
            self.outlineView.setModel(self._model)
            self.outlineView.setRootIndex(self.currentIndex)

            try:
                selection_changed = self.outline_context.selection_changed
                if selection_changed is not None:
                    self.outlineView.selectionModel().selectionChanged.connect(
                        selection_changed,
                        AUC,
                    )
                    self.outlineView.clicked.connect(
                        selection_changed,
                        AUC,
                    )
                if self.main_editor is not None:
                    self.outlineView.clicked.connect(
                        self.main_editor.updateTargets,
                        AUC,
                    )
            except TypeError:
                pass

        if item and item.isText():
            self.txtRedacText.setCurrentModelIndex(self.currentIndex)
            self.stack.setCurrentIndex(0)  # Single text item
        else:
            self.txtRedacText.setCurrentModelIndex(QModelIndex())

        try:
            self._model.dataChanged.connect(self.modelDataChanged, AUC)
            self._model.rowsAboutToBeRemoved.connect(self.rowsAboutToBeRemoved, AUC)
        except TypeError:
            pass

        self.updateStatusBar()
        self._updateMarkdownModeButtonVisibility()
        self.markdownModeButton.raise_()
        self.undoButton.raise_()
        self.redoButton.raise_()
        if self.markupProfileButton is not None:
            self.markupProfileButton.raise_()

    def setCurrentModelIndex(self, index=None):
        if index and index.isValid():
            self.currentIndex = index
            self._model = index.model()
            self.currentID = self._model.ID(index)
        else:
            self.currentIndex = QModelIndex()
            self.currentID = None

        if self.pageType is not None:
            item = (
                self.currentIndex.internalPointer()
                if self.currentIndex.isValid()
                else None
            )
            self.pageType.set_item(item)

        if self._model:
            self.setView()

    def updateIndexFromID(self, fallback=None, ignore=None):
        """
        Index might have changed (through drag an drop), so we keep current
        item's ID and update index. Item might have been deleted too.

        It will ignore the passed model item to avoid ambiguity during times
        of inconsistent state.
        """
        idx = self._model.getIndexByID(self.currentID, ignore=ignore)

        # If we have an ID but the ID does not exist, it has been deleted.
        if self.currentID and idx == QModelIndex():
            # If we are given a fallback item to display, do so.
            if fallback:
                self.setCurrentModelIndex(fallback)
                self._syncActiveEditorSelection()
            else:
                # After tab closing is implemented, any calls to `updateIndexFromID`
                # should be re-evaluated to match the desired behaviour.
                raise NotImplementedError("implement tab closing")

        # Item has been moved
        elif idx != self.currentIndex:
            # We update the index
            self.currentIndex = idx
            self.setView()

    def _syncActiveEditorSelection(self):
        """Refresh global selection only when this is the visible tab."""
        if (
            self.main_editor is not None
            and self.main_editor.currentEditor() is self
        ):
            self.main_editor.tabChanged()

    def modelDataChanged(self, topLeft, bottomRight):
        if not self.currentIndex.isValid():
            return  # Just to be safe.

        # We are only concerned with minor changes to the current index,
        # so there is no need to call updateIndexFromID() nor setView().
        if topLeft.row() <= self.currentIndex.row() <= bottomRight.row():
            if self.pageType is not None:
                self.pageType.refresh(force=True)
            for state in self.pageTypeStates:
                state.refresh(force=True)
            self.updateTabTitle()
            self.updateStatusBar()

    def rowsAboutToBeRemoved(self, parent, first, last):
        if not self.currentIndex.isValid():
            return  # Just to be safe.

        # Look for a common ancestor to verify whether the deleted rows include our index in their hierarchy.
        childItem = self.currentIndex
        ancestorCandidate = childItem.parent()  # start at folder above current item
        while (ancestorCandidate != parent):
            childItem = ancestorCandidate
            ancestorCandidate = childItem.parent()

            if not ancestorCandidate.isValid():
                return  # we ran out of ancestors without finding the matching QModelIndex

        # My sanity advocates a healthy dose of paranoia. (Just to be safe.)
        if ancestorCandidate != parent:
            return  # we did not find our shared ancestor

        # Verify our origins come from the relevant first..last range.
        if first <= childItem.row() <= last:
            # If the row in question was actually moved, there is a duplicate item
            # already inserted elsewhere in the tree. Try to update this tab view,
            # but make sure we exclude ourselves from the search for a replacement.
            self.updateIndexFromID(fallback=parent, ignore=self.currentIndex.internalPointer())

    def updateStatusBar(self):
        if self.main_editor is not None:
            self.main_editor.tabChanged()

    def toggleSpellcheck(self, v):
        self.spellcheck = v
        self.toggledSpellcheck.emit(v)

    def setDict(self, dct):
        self.currentDict = dct
        self.dictChanged.emit(dct)

    ###############################################################################
    # DOCUMENT COMMAND ROUTING
    ###############################################################################

    def getCurrentItemView(self):
        """
        Returns the current item view, between txtRedacText, outlineView and
        corkView. If folder/text view, returns None. (Because handled
        differently)
        """

        if self.stack.currentIndex() == 0:
            return self.txtRedacText
        elif self.folderView == "outline":
            return self.outlineView
        elif self.folderView == "cork":
            return self.corkView
        else:
            return None

    def document_command_target(self, command):
        if command in {
            DocumentCommand.SPLIT_DIALOG,
            DocumentCommand.SPLIT_CURSOR,
            DocumentCommand.MERGE,
        }:
            return self
        return self.getCurrentItemView()

    def splitDialog(self):
        """
        Opens a dialog to split selected items.
        """
        if self.getCurrentItemView() == self.txtRedacText:
            # Text editor
            if not self.currentIndex.isValid():
                return

            sel = self.txtRedacText.textCursor().selectedText()
            # selectedText uses \u2029 instead of \n, no idea why.
            sel = sel.replace("\u2029", "\n")
            open_split_dialog(
                self,
                [self.currentIndex],
                self.editor_context.outline_model.rootItem,
                mark=sel,
            )

        elif self.getCurrentItemView():
            # One of the views
            self.getCurrentItemView().splitDialog()

    def splitCursor(self):
        """
        Splits items at cursor position. If there is a selection, that selection
        becomes the new item's title.

        Call context: Only works when editing a file.
        """

        if not self.currentIndex.isValid():
            return

        if self.getCurrentItemView() == self.txtRedacText:
            c = self.txtRedacText.textCursor()

            title = c.selectedText()
            # selection can be backward
            pos = min(c.selectionStart(), c.selectionEnd())

            item = self.currentIndex.internalPointer()

            item.splitAt(pos, len(title))

    def merge(self):
        """
        Merges selected items together.

        Call context: Multiple selection, same parent.
        """
        if self.getCurrentItemView() == self.txtRedacText:
            # Text editor, nothing to merge
            pass

        elif self.getCurrentItemView():
            # One of the views
            self.getCurrentItemView().merge()
