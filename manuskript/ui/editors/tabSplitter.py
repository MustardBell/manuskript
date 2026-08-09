#!/usr/bin/env python
# --!-- coding: utf8 --!--
import locale, os

from PyQt5.QtCore import QModelIndex, QRect, QPoint, Qt, QObject, QSize
from PyQt5.QtGui import QIcon, QPalette
from PyQt5.QtGui import QDropEvent, QDragEnterEvent
from PyQt5.QtWidgets import QWidget, QPushButton

from manuskript.functions import appPath
from manuskript.ui import style
from manuskript.ui.editors.tabSplitter_ui import Ui_tabSplitter
from manuskript.ui.views.text_editor_settings import (
    DefaultTextEditorSettings,
)

import logging
LOGGER = logging.getLogger(__name__)

class tabSplitter(QWidget, Ui_tabSplitter):
    """
    `tabSplitter` is used to have multiple `outlineItem`s open, either in tabs
    and/or in split views. Each tab contains an `editorWidget` which is responsible
    for showing one single `outlineItem` in several ways.

    `tabSplitter` is managed mainly through the `mainEditor` which is responsible
    for opening indexes and such.

    `tabSplitter` main widget is a `QSplitter` named `self.splitter`. It contains one
    `QTabWidget` called `self.tab`. A second `tabSplitter` can be loaded through
    `self.split` in `self.splitter`. That way, a single `tabSplitter` can split
    indefinitely.

    `tabSplitter` also has two buttons:

     1. `self.btnSplit`: used to split and unsplit
     2. `self.btnTarget`: toggles whether `self.tab` is a target to open any
        selected outlineItem in any other views.
    """

    def __init__(
        self,
        parent=None,
        mainEditor=None,
        editor_context=None,
    ):
        QWidget.__init__(self, parent)
        self.setupUi(self)
        self.editor_context = editor_context
        self._focus_source = None
        self.settings = (
            editor_context.text_editor.settings
            if editor_context is not None
            and editor_context.text_editor is not None
            else DefaultTextEditorSettings()
        )

        # try:
        #     self.tab.setTabBarAutoHide(True)
        # except AttributeError:
        #     LOGGER.info("Install Qt 5.4 or higher to use tab bar auto-hide in editor.")

        # Button to split
        self.btnSplit = QPushButton(self)
        self.btnSplit.setGeometry(QRect(0, 0, 24, 24))
        self.btnSplit.setMinimumSize(QSize(24, 24))
        self.btnSplit.setMaximumSize(QSize(24, 24))
        # self.btnSplit.setCheckable(True)
        self.btnSplit.setFlat(True)
        self.btnSplit.setObjectName("btnSplit")
        self.btnSplit.installEventFilter(self)
        self.btnSplit.clicked.connect(self.split)

        # Button to set target
        self.isTarget = False
        self.btnTarget = QPushButton(QIcon.fromTheme("set-target"), "", self)
        self.btnTarget.setGeometry(QRect(25, 0, 24, 24))
        self.btnTarget.setMinimumSize(QSize(24, 24))
        self.btnTarget.setMaximumSize(QSize(24, 24))
        # self.btnTarget.setCheckable(True)
        self.btnTarget.setFlat(True)
        self.btnTarget.setObjectName("btnTarget")
        self.btnTarget.clicked.connect(self.setTarget)
        self.btnTarget.setToolTip(self.tr("Open selected items in that view."))
        self.updateTargetIcon(self.isTarget)

        self.mainEditor = mainEditor or parent

        self.secondTab = None
        # The child holding this node's own side, once that side has been
        # divided. While it is None this node owns ``self.tab`` directly;
        # when it is set this node is a branch and its tab is empty.
        self.firstTab = None
        self.splitState = 0
        self.focusTab = 1
        self.closeSplit()

        self.updateStyleSheet()

        self.tab.tabCloseRequested.connect(self.closeTab)
        self.tab.currentChanged.connect(self.mainEditor.tabChanged)

        self.setAcceptDrops(True)

    def set_focus_source(self, focus_source):
        """Use the owning workspace's focus stream for pane activation."""
        if focus_source is self._focus_source:
            return
        if self._focus_source is not None:
            self._focus_source.unsubscribe(self.focusChanged)
        self._focus_source = focus_source
        if focus_source is not None:
            focus_source.subscribe(self.focusChanged)
        for child in self.children_areas():
            child.set_focus_source(focus_source)

    def dispose(self):
        """Release focus consumers in a pane subtree being discarded."""
        self.set_focus_source(None)
        for index in range(self.tab.count()):
            editor = self.tab.widget(index)
            dispose = getattr(editor, "dispose", None)
            if callable(dispose):
                dispose()
        for child in self.children_areas():
            child.dispose()

    def set_context(self, context):
        self.editor_context = context
        if context is not None and context.text_editor is not None:
            self.settings = context.text_editor.settings
            self.updateStyleSheet()
        for child in self.children_areas():
            child.set_context(context)

    def children_areas(self):
        """The areas nested directly inside this one, in order."""
        return tuple(
            child
            for child in (self.firstTab, self.secondTab)
            if child is not None
        )

    def leaves(self):
        """Every area that holds documents, left to right, top to bottom.

        A node that has divided its own side holds none itself; its
        documents live in the child that took that side over.
        """
        if self.firstTab is not None:
            found = list(self.firstTab.leaves())
        else:
            found = [self]
        if self.secondTab is not None:
            found.extend(self.secondTab.leaves())
        return found

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat('application/xml'):
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if self.editor_context is None:
            event.ignore()
            return
        outline_model = self.editor_context.outline_model
        items = outline_model.decodeMimeData(event.mimeData())
        if not items:
            event.ignore()
            return
        itemID = items[0].ID()
        itemIndex = outline_model.getIndexByID(itemID)
        self.mainEditor.setCurrentModelIndex(itemIndex, tabWidget = self.tab)
        event.accept()

    def updateStyleSheet(self):
        self.setStyleSheet(style.mainEditorTabSS(self.settings))
        for child in self.children_areas():
            child.updateStyleSheet()

    ###############################################################################
    # TABS
    ###############################################################################

    def closeTab(self, index):
        w = self.tab.widget(index)
        self.tab.removeTab(index)
        w.setCurrentModelIndex(QModelIndex())
        dispose = getattr(w, "dispose", None)
        if callable(dispose):
            dispose()
        w.deleteLater()
        self.collapseIfEmpty()

    def parent_area(self):
        """The area this one is a half of, if it is a half of one."""
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, tabSplitter):
                return parent
            parent = parent.parentWidget()
        return None

    def collapseIfEmpty(self):
        """Give an emptied half's space back instead of leaving a frame.

        Closing the last document in one half of a split left that half
        standing: an empty tab bar and a splitter handle, holding space
        nothing was using and offering nothing to do.

        Only for an area that holds documents itself. A nested area's own
        tab widget is legitimately empty -- its documents live in the child
        that took its side over -- and collapsing on that would undo the
        nesting the moment it was made.
        """
        if self.firstTab is not None or self.tab.count():
            return False

        neighbour = self.secondTab
        if neighbour is not None:
            if neighbour.children_areas():
                # The other half is itself divided. Absorbing a subtree
                # means rebuilding its editors, and an editor losing its
                # cursor because a neighbour closed a tab is worse than the
                # frame this leaves behind.
                return False
            # Take the neighbour's documents and close the split, which is
            # what collapsing a nested side already does one level down.
            while neighbour.tab.count():
                widget = neighbour.tab.widget(0)
                title = neighbour.tab.tabText(0)
                neighbour.tab.removeTab(0)
                self.tab.addTab(widget, title)
            self.closeSplit()
            if self.tab.count():
                return True
            # The neighbour had nothing either, so this area has no more
            # reason to exist than it did a moment ago. Ask again, now that
            # it is no longer split.
            return self.collapseIfEmpty()

        parent = self.parent_area()
        if parent is None:
            # The only area there is. An editor with nothing open is a
            # legitimate state, not an empty frame beside something.
            return False
        if parent.secondTab is self:
            parent.closeSplit()
            return True
        if parent.firstTab is self:
            # This area *was* the parent's own side. Handing it back leaves
            # the parent's own side empty in turn, so it asks itself the
            # same question.
            parent.collapseOwnSide()
            parent.collapseIfEmpty()
            return True
        return False

    def tabOpenIndexes(self):
        if self.editor_context is None:
            return []
        outline_model = self.editor_context.outline_model
        sel = []
        for i in range(self.tab.count()):
            sel.append(outline_model.ID(self.tab.widget(i).currentIndex))
        return sel

    def openIndexes(self):
        r = [
            self.splitState,
            self.tabOpenIndexes(),
            self.secondTab.openIndexes() if self.secondTab else None,
        ]
        return r

    def describe(self):
        """This area's arrangement, as a document area node.

        Says the shape rather than implying it: a divided own side is a
        split whose first half is itself whatever that child is.
        """
        from manuskript.domain.document_area import (
            HORIZONTAL,
            VERTICAL,
            Split,
            TabGroup,
        )

        if self.firstTab is not None:
            own = self.firstTab.describe()
        else:
            own = TabGroup(
                documents=self.tabOpenIndexes(),
                current=max(0, self.tab.currentIndex()),
            )
        if self.secondTab is None:
            return own
        return Split(
            orientation=(
                VERTICAL
                if self.splitter.orientation() == Qt.Vertical
                else HORIZONTAL
            ),
            first=own,
            second=self.secondTab.describe(),
            sizes=tuple(self.splitter.sizes()),
        )

    def restore(self, node):
        """Put this area into an arrangement, dividing as it requires."""
        from manuskript.domain.document_area import Split, VERTICAL

        if isinstance(node, Split):
            orientation = (
                Qt.Vertical if node.orientation == VERTICAL
                else Qt.Horizontal
            )
            if self.secondTab is None:
                self.split(state=2 if orientation == Qt.Vertical else 1)
            self.splitter.setOrientation(orientation)
            self.splitState = 2 if orientation == Qt.Vertical else 1
            if isinstance(node.first, Split):
                # Both halves divided, which is the arrangement the comb
                # could not hold.
                self.nestOwnSide(orientation)
                self.firstTab.restore(node.first)
            else:
                self._restoreGroup(node.first)
            self.secondTab.restore(node.second)
            if node.sizes and len(node.sizes) == self.splitter.count():
                self.splitter.setSizes(list(node.sizes))
            return
        self._restoreGroup(node)

    def _restoreGroup(self, group):
        """Open one tab group's documents in this area's own tabs, on the
        tab that was in front.

        Opening documents leaves the last one current, so without the
        final step every area came back showing whichever document was
        opened last rather than the one being read. The group records
        ``current`` for exactly this, and nothing was reading it.

        Documents the outline no longer holds are skipped rather than
        opened. A recorded arrangement can name something since deleted --
        or belong to a different project entirely -- and asking to open an
        id that resolves to nothing produced a tab bound to an invalid
        index: a phantom in the tab bar, reported by tabOpenIndexes as a
        document with no identity at all.
        """
        if self.editor_context is None:
            return
        outline_model = self.editor_context.outline_model
        target = (
            self.firstTab.tab if self.firstTab is not None else self.tab
        )
        for document in group.documents:
            index = outline_model.getIndexByID(document)
            if index is None or not index.isValid():
                continue
            self.mainEditor.setCurrentModelIndex(
                index,
                newTab=True,
                tabWidget=target,
            )
        if 0 <= group.current < target.count():
            target.setCurrentIndex(group.current)

    def restoreOpenIndexes(self, openIndexes):

        try:
            if openIndexes[1]:
                self.split(state=openIndexes[0])

            if self.editor_context is None:
                return
            outline_model = self.editor_context.outline_model
            for i in openIndexes[1]:
                idx = outline_model.getIndexByID(i)
                self.mainEditor.setCurrentModelIndex(idx, newTab=True)

            if openIndexes[2]:
                self.focusTab = 2
                self.secondTab.restoreOpenIndexes(openIndexes[2])

        except:
            # Cannot load open indexes. Let's simply open root.
            self.mainEditor.setCurrentModelIndex(QModelIndex(), newTab=True)

    ###############################################################################
    # TARGET
    ###############################################################################

    def setTarget(self):
        self.isTarget = not self.isTarget
        self.updateTargetIcon(self.isTarget)

    def updateTargetIcon(self, val):
        icon = QIcon.fromTheme("set-target", QIcon(appPath(os.path.join("icons", "NumixMsk", "256x256", "actions", "set-target.svg"))))
        if not val:
            icon = QIcon(icon.pixmap(128, 128, icon.Disabled))
        self.btnTarget.setIcon(icon)

    ###############################################################################
    # SPLITTER
    ###############################################################################

    def split(self, toggled=None, state=None):

        if state == None and self.splitState == 0 or state == 1:
            if self.secondTab == None:
                self.addSecondTab()

            self.splitState = 1
            self.splitter.setOrientation(Qt.Horizontal)
            self.equalizeSplit()
            # self.btnSplit.setChecked(True)
            self.btnSplit.setIcon(QIcon.fromTheme("split-vertical"))
            self.btnSplit.setToolTip(self.tr("Split horizontally"))

        elif state == None and self.splitState == 1 or state == 2:
            if self.secondTab == None:
                self.addSecondTab()

            self.splitter.setOrientation(Qt.Vertical)
            self.splitState = 2
            self.equalizeSplit()
            # self.btnSplit.setChecked(True)
            self.btnSplit.setIcon(QIcon.fromTheme("split-horizontal"))
            self.btnSplit.setToolTip(self.tr("Close split"))

        else:
            self.closeSplit()

    def divideOwnSide(self, orientation=Qt.Horizontal):
        """Divide this area's own half in two, which the comb could not do.

        Splitting only ever added a neighbour, so the first half stayed a
        bare tab group for ever. This divides that half itself: it moves
        into a child of its own, and that child then gains a neighbour.
        """
        state = 2 if orientation == Qt.Vertical else 1
        if self.secondTab is None:
            # Nothing beside it yet, so this area *is* its own half and
            # dividing it is an ordinary split.
            self.split(state=state)
            return self
        child = self.nestOwnSide(orientation)
        if child.secondTab is None:
            child.split(state=state)
        return child

    def nestOwnSide(self, orientation=Qt.Horizontal):
        """Move this area's own half into a child, without dividing it.

        The structural half of dividing: afterwards this node holds no
        documents and is free to have either half divided. Restoring a
        stored arrangement uses this and then tells the child what shape
        to take.

        Only meaningful once something is beside it -- an area with no
        neighbour has no "own half" distinct from itself.
        """
        if self.secondTab is None:
            return None
        if self.firstTab is not None:
            return self.firstTab
        child = tabSplitter(
            mainEditor=self.mainEditor,
            editor_context=self.editor_context,
        )
        child.set_focus_source(self._focus_source)
        child.setObjectName(self.objectName() + "/1")
        child.splitter.setObjectName(self.splitter.objectName() + "/1")
        # The documents move with the side they were on.
        while self.tab.count():
            widget = self.tab.widget(0)
            title = self.tab.tabText(0)
            self.tab.removeTab(0)
            child.tab.addTab(widget, title)
        self.tab.hide()
        self.splitter.insertWidget(0, child)
        self.splitter.setOrientation(orientation)
        self.firstTab = child
        self.splitter.setStretchFactor(0, 10)
        self.splitter.setStretchFactor(1, 10)
        self.equalizeSplit()
        return child

    def collapseOwnSide(self):
        """Undo nesting, taking the documents back into this area."""
        child = self.firstTab
        if child is None:
            return
        child.collapseOwnSide()
        while child.tab.count():
            widget = child.tab.widget(0)
            title = child.tab.tabText(0)
            child.tab.removeTab(0)
            self.tab.addTab(widget, title)
        self.firstTab = None
        child.setParent(None)
        child.set_focus_source(None)
        child.deleteLater()
        self.tab.show()

    def addSecondTab(self):
        self.secondTab = tabSplitter(
            mainEditor=self.mainEditor,
            editor_context=self.editor_context,
        )
        self.secondTab.set_focus_source(self._focus_source)
        self.secondTab.setObjectName(self.objectName() + "_")
        self.secondTab.splitter.setObjectName(self.splitter.objectName() + "_")

        self.splitter.addWidget(self.secondTab)
        self.splitter.setStretchFactor(0, 10)
        self.splitter.setStretchFactor(1, 10)

        if self.mainEditor.currentEditor():
            idx = self.mainEditor.currentEditor().currentIndex
            self.focusTab = 2
            self.mainEditor.setCurrentModelIndex(idx)

    def equalizeSplit(self):
        """Give this area's halves the same size.

        Stretch factors decide how a splitter hands out space it *gains*,
        not how it distributes what it already has -- that comes from the
        child widgets' size hints. A pane built empty asks for very little,
        so a fresh split appeared as a sliver beside the editor instead of
        half of it, and the stretch factors set on either side of it never
        had anything to do.

        Silent when the splitter has not been laid out yet: a width of zero
        divides into halves of zero, and a restored arrangement sets its own
        remembered sizes anyway.
        """
        splitter = self.splitter
        # Visible panes only. Nesting leaves this area's own tab widget in
        # the splitter, hidden, once its documents have moved into a child,
        # so counting panes would divide the space three ways to fill two.
        shown = [
            index for index in range(splitter.count())
            if not splitter.widget(index).isHidden()
        ]
        if len(shown) < 2:
            return False
        extent = (
            splitter.width()
            if splitter.orientation() == Qt.Horizontal
            else splitter.height()
        )
        if extent <= 0:
            return False
        share = extent // len(shown)
        splitter.setSizes([
            share if index in shown else 0
            for index in range(splitter.count())
        ])
        return True

    def closeSplit(self):
        self.collapseOwnSide()
        st = self.secondTab
        l = []
        while st:
            l.append(st)
            st = st.secondTab

        for st in reversed(l):
            st.setParent(None)
            st.dispose()
            st.deleteLater()

        self.focusTab = 1
        self.secondTab = None
        # self.btnSplit.setChecked(False)
        self.splitState = 0
        self.btnSplit.setIcon(QIcon.fromTheme("split-close"))
        self.btnSplit.setToolTip(self.tr("Split vertically"))

        if len(l):
            self.mainEditor.tabChanged()

    # def resizeEvent(self, event):
    #     r = self.geometry()
    #     r.moveLeft(0)
    #     r.moveTop(0)
    #     self.splitter.setGeometry(r)
    #     self.btnSplit.setGeometry(QRect(0, 0, 24, 24))

    def focusChanged(self, old, new):
        if self.secondTab == None or new == None:
            return

        oldFT = self.focusTab
        while new:
            if new == self.tab or new == self.firstTab:
                # Its own half, whether it holds the tabs directly or
                # has been divided into a child.
                self.focusTab = 1
                new = None
            elif new == self.secondTab:
                self.focusTab = 2
                new = None
            else:
                new = new.parent()

        if self.focusTab != oldFT:
            self.mainEditor.tabChanged()

    def eventFilter(self, object, event):
        if object == self.btnSplit and event.type() == event.HoverEnter:
            # self.setAutoFillBackground(True)
            # self.setBackgroundRole(QPalette.Highlight)

            # self.splitter.setAutoFillBackground(True)
            # self.splitter.setStyleSheet("""QSplitter#{}{{
            #     border:1px solid darkblue;
            #     }}""".format(self.splitter.objectName()))

            self.setStyleSheet(style.mainEditorTabSS(self.settings) + """
                QSplitter#{name},
                QSplitter#{name} > QWidget > QSplitter{{
                    border:3px solid {color};
                }}""".format(
                    name=self.splitter.objectName(),
                    color=style.highlight))
        elif object == self.btnSplit and event.type() == event.HoverLeave:
            # self.setAutoFillBackground(False)
            # self.setBackgroundRole(QPalette.Window)

            # self.splitter.setStyleSheet("""QSplitter#{}{{
            #     border: 1px solid transparent;
            #     }}""".format(self.splitter.objectName()))

            self.setStyleSheet(style.mainEditorTabSS(self.settings))
        return QWidget.eventFilter(self, object, event)
