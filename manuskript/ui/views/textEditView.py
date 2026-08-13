#!/usr/bin/env python
# --!-- coding: utf8 --!--
import re, textwrap

from PyQt5.Qt import QApplication
from PyQt5.QtCore import QTimer, QModelIndex, Qt, QEvent, pyqtSignal, QLocale, QPersistentModelIndex, QMutex
from PyQt5.QtGui import QTextBlockFormat, QTextCharFormat, QTextDocument, QFont, QColor, QIcon, QKeySequence, QMouseEvent, QTextCursor
from PyQt5.QtWidgets import (
    QAction,
    QMenu,
    QTextEdit,
    QToolTip,
    QWIDGETSIZE_MAX,
    QWidget,
    qApp,
)

from manuskript.commands import DocumentCommand
from manuskript.enums import Outline, World, Character, Plot
from manuskript import functions as F
from manuskript.models import outlineModel, outlineItem
from manuskript.ui.highlighters import BasicHighlighter
from manuskript.domain.text import plain_text
from manuskript.ui import style as S
from manuskript.functions import Spellchecker
from manuskript.models.characterModel import Character, CharacterInfo
from manuskript.ui.views.text_editor_settings import (
    DefaultTextEditorSettings,
)


import logging
LOGGER = logging.getLogger(__name__)

class textEditView(QTextEdit):

    #: Emitted when this view starts showing a different QTextDocument.
    #: Qt has no such signal, and swapping a document silently leaves
    #: anything watching the old one watching nothing at all.
    documentReplaced = pyqtSignal()

    def __init__(self, parent=None, index=None, html=None, spellcheck=None,
                 highlighting=False, dict="", autoResize=False,
                 settings=None, highlighter_class=None):
        QTextEdit.__init__(self, parent)
        self._column = Outline.text
        self._index = None
        self._indexes = None
        self._model = None
        self._placeholderText = self.placeholderText()
        self._updating = QMutex()
        self._item = None
        #: The project's buffer for this document, once bound to one. Views
        #: sharing it are viewports on one text rather than copies of it.
        self._buffer = None
        #: What this view was showing when it stood down, so it can pick the
        #: same document up again when it is on screen once more.
        self._releasedIndex = None
        #: This view's own highlighter. Text may be shared, but character
        #: formats are presentation state and therefore stay on this view's
        #: projection document.
        self._ownHighlighter = None
        self._highlighting = highlighting
        self._textFormat = "text"
        self.setAcceptRichText(False)
        # When setting up a theme, this becomes true.
        self._fromTheme = False
        self._themeData = None
        self._highlighterClass = highlighter_class or BasicHighlighter
        self.text_editor_context = None
        self.settings = (
            settings
            if settings is not None
            else DefaultTextEditorSettings()
        )

        if spellcheck == None:
            spellcheck = self.settings.spellcheck

        self.spellcheck = spellcheck
        self.currentDict = dict if dict else self.settings.dict
        self._defaultFontSize = qApp.font().pointSize()
        self.highlighter = None
        self.setAutoResize(autoResize)
        self._defaultBlockFormat = QTextBlockFormat()
        self._defaultCharFormat = QTextCharFormat()
        self.highlightWord = ""
        self.highligtCS = False
        self._dict = None
        self._tooltip = { 'depth' : 0, 'active' : 0 }

        # Submit text changed only after 500ms without modifications
        self._disposed = False
        self.updateTimer = QTimer(self)
        self.updateTimer.setInterval(500)
        self.updateTimer.setSingleShot(True)
        self.updateTimer.timeout.connect(self.submit)

        self.updateTimer.stop()
        self.updateTimerConnection = self.document().contentsChanged.connect(self.updateTimer.start, F.AUC)

        self.setEnabled(False)

        if index:
            self.setCurrentModelIndex(index)

        elif html:
            self.document().setHtml(html)
            self.setReadOnly(True)

        # Spellchecking
        if self.spellcheck:
            self._dict = Spellchecker.getDictionary(self.currentDict)

        if not self._dict:
            self.spellcheck = False

        if self._highlighting and not self.highlighter:
            self.highlighter = self._highlighterClass(self)
            self.highlighter.setDefaultBlockFormat(self._defaultBlockFormat)

    @property
    def highlighter(self):
        """The highlighter for this view's local document projection."""
        return self._ownHighlighter

    @highlighter.setter
    def highlighter(self, value):
        self._ownHighlighter = value

    def set_text_editor_context(self, context):
        self.text_editor_context = context
        if context is not None:
            self.settings = context.settings
    
    def dispose(self):
        """Stop every callback before the native editor is destroyed.

        Tabs are removed synchronously and deleted by Qt on the next event
        turn.  A zero-delay layout task or the private submit timer can run in
        that interval, when the editor has already released its project
        document.  Treat those callbacks as owned resources instead of
        relying on Python garbage collection to eventually destroy them.
        """
        if self._disposed:
            return
        self._disposed = True
        self.releaseWorkspaceFocus()
        self._releaseSharedBuffer()
        self.disconnectDocument()
        timer = self.updateTimer
        if timer is not None:
            timer.stop()
            try:
                timer.timeout.disconnect(self.submit)
            except (TypeError, RuntimeError):
                pass
        self.updateTimer = None
        self.updateTimerConnection = None
        model = self._model
        if model is not None:
            try:
                model.dataChanged.disconnect(self.update)
            except (TypeError, RuntimeError):
                pass
        self._model = None
        self._index = QModelIndex()
        self._indexes = None

    def setModel(self, model):
        self._model = model
        try:
            self._model.dataChanged.connect(self.update, F.AUC)
        except TypeError:
            pass

    def setColumn(self, col):
        self._column = col

    def setHighlighting(self, val):
        self._highlighting = val

    def setDefaultBlockFormat(self, bf):
        self._defaultBlockFormat = bf
        if self.highlighter:
            self.highlighter.setDefaultBlockFormat(bf)

    def setCurrentModelIndex(self, index):
        self._indexes = None
        self._releaseSharedBuffer()
        if index.isValid():
            self.setEnabled(True)
            if index.column() != self._column:
                index = index.sibling(index.row(), self._column)
            self._index = QPersistentModelIndex(index)

            self.setPlaceholderText(self._placeholderText)

            if not self._model:
                self.setModel(index.model())

            shared = self._attachSharedBuffer()
            self.setupEditorForIndex(self._index)
            self.loadFontSettings()
            if shared:
                # Only when this view is the first to show the document:
                # a second window opening it must not wipe the undo
                # history of the person already working in the first.
                if len(self._buffer.views) == 1:
                    self._buffer.settle()
            else:
                self.updateText()

        else:
            self._index = QModelIndex()

            self.setPlainText("")
            self.setEnabled(False)

    # ------------------------------------------------- the shared buffer

    @property
    def _bufferRegistry(self):
        """The project's buffers, if this editor is bound to a project."""
        return getattr(self.text_editor_context, "document_buffers", None)

    def _documentIdentity(self):
        """What two views would both call this document, or None.

        Only the outline names its documents in a way two views can agree
        on, and only its text is the thing two windows are expected to be
        editing at once. Read through the model rather than through
        internalPointer(), which is a Python item here and raw C++
        internals in the QStandardItemModel-based models.
        """
        model = self._model
        index = self._index
        if model is None or index is None or not index.isValid():
            return None
        if not hasattr(model, "getIndexByID"):
            return None
        value = model.data(index.sibling(index.row(), Outline.ID))
        return str(value) if value else None

    def _attachSharedBuffer(self):
        """Become a viewport onto the project's one buffer for this
        document, rather than keeping private text of my own.

        Answers whether that happened. It does not for editors the sharing
        does not apply to -- a multiple selection, a character's notes, a
        read-only html view -- and those keep the private document and the
        private timer they always had.
        """
        registry = self._bufferRegistry
        if registry is None:
            return False
        buffer = registry.buffer_for(
            self._model, self._index, self._column,
            self._documentIdentity(),
            view=self,
        )
        if buffer is None:
            return False
        # The buffer owns the timer now. Leaving this view's own connected
        # would mean two things submitting the same text.
        self.disconnectDocument()
        # Let go of any highlighter of my own before the swap. setDocument
        # deletes a document the editor created, and a highlighter left
        # pointing at a deleted document takes the interpreter down later,
        # during a garbage collection with no stack that names this code.
        if self._ownHighlighter is not None:
            self._ownHighlighter.setDocument(None)
            self._ownHighlighter.deleteLater()
            self._ownHighlighter = None
        self._buffer = buffer
        self.setDocument(buffer.document_for(self))
        # The highlighter is built by setupEditorForIndex on this projection.
        # Another pane showing the same text has another projection, so its
        # wrap width and presentation formatting cannot alter this one.
        self.documentReplaced.emit()
        return True

    def standDown(self):
        """Let go of the document while nothing on screen shows this view.

        This remains useful for releasing hidden tabs and their formatting
        work even though each visible view now owns an independent layout.
        """
        index = self._index
        if index is None or not index.isValid():
            return False
        self._releasedIndex = QPersistentModelIndex(index)
        self.setCurrentModelIndex(QModelIndex())
        return True

    def resume(self):
        """Show again what standing down let go of."""
        index = self._releasedIndex
        self._releasedIndex = None
        if index is None or not index.isValid():
            return False
        model = index.model()
        self.setCurrentModelIndex(model.index(
            index.row(), index.column(), index.parent(),
        ))
        return True

    def _releaseSharedBuffer(self):
        """Stop showing a shared buffer, without taking it from others.

        Text of my own first, then let go. setDocument does not take
        ownership of a document somebody else parented, so a buffer
        released while this editor was still displaying its document would
        take the document with it and leave the editor pointing at nothing.
        """
        buffer = getattr(self, "_buffer", None)
        if buffer is None:
            return
        self._buffer = None
        if self._ownHighlighter is not None:
            self._ownHighlighter.setDocument(None)
            self._ownHighlighter.deleteLater()
            self._ownHighlighter = None
        self.disconnectDocument()
        self.setDocument(QTextDocument(self))
        self.reconnectDocument()
        self.documentReplaced.emit()
        registry = self._bufferRegistry
        if registry is not None:
            registry.detach(self, buffer)

    def currentIndex(self):
        """
        Getter function used to normalized views access with QAbstractItemViews.
        """
        if self._index:
            return self._index
        else:
            return QModelIndex()

    def getSelection(self):
        """
        Getter function used to normalized views access with QAbstractItemViews.
        """
        return [self.currentIndex()]

    def setCurrentModelIndexes(self, indexes):
        self._index = None
        self._indexes = []

        for i in indexes:
            if i.isValid():
                self.setEnabled(True)
                if i.column() != self._column:
                    i = i.sibling(i.row(), self._column)
                self._indexes.append(QModelIndex(i))

                if not self._model:
                    self.setModel(i.model())

        self.updateText()

    def setupEditorForIndex(self, index):
        # Setting highlighter
        if self._highlighting:
            if self.highlighter is not None:
                self.highlighter.setDocument(None)
                self.highlighter.deleteLater()
            self.highlighter = self._highlighterClass(self)
            self.highlighter.setDefaultBlockFormat(self._defaultBlockFormat)
            self.highlighter.updateColorScheme()

    def loadFontSettings(self):
        if self._fromTheme or \
            not self._index or \
                type(self._index.model()) != outlineModel or \
                self._column != Outline.text:
            return

        opt = self.settings.textEditor
        f = QFont()
        f.fromString(opt["font"])
        background = (opt["background"] if not opt["backgroundTransparent"]
                      else "transparent")
        foreground = opt["fontColor"]  # if not opt["backgroundTransparent"]
        #                               else S.text
        # self.setFont(f)
        editor_style = """QStackedWidget#markdownEditorHost {{
            background: {bg};
            }}
            QTextEdit{{
            background: {bg};
            color: {foreground};
            font-family: {ff};
            font-size: {fs};
            margin: {mTB}px {mLR}px;
            }}
            """.format(
            bg=background,
            foreground=foreground,
            ff=f.family(),
            fs="{}pt".format(str(f.pointSize())),
            mTB=opt["marginsTB"],
            mLR=opt["marginsLR"],
        )
        style_owner = (
            getattr(self, "_presentationHost", None)
            or self
        )
        # The outer editor layout centers its direct child when a maximum
        # width is configured. Once Markdown modes introduced a stacked host,
        # constraining the inner QTextEdit pinned the text column to the
        # host's left edge. Constrain the layout-owned widget instead so every
        # presentation mode shares the native centered geometry.
        maximum_width = opt["maxWidth"] or QWIDGETSIZE_MAX
        configure_width = getattr(
            style_owner,
            "setConfiguredMaximumWidth",
            None,
        )
        if callable(configure_width):
            configure_width(maximum_width)
        else:
            style_owner.setMaximumWidth(maximum_width)
        style_owner.setStyleSheet(editor_style)
        if style_owner is not self:
            self.setStyleSheet("")
        self._defaultFontSize = f.pointSize()

        # Paint the layout-owned canvas behind a width-constrained editor.
        # With a MarkdownEditorHost, that canvas is one level above the source
        # QTextEdit; standalone editors retain the original direct-parent
        # behavior. Keep the exact QWidget check so full-screen containers are
        # not restyled.
        background_parent = style_owner.parentWidget()
        if (
            background_parent is not None
            and background_parent.__class__ == QWidget
        ):
            background_parent.setStyleSheet("""
                QWidget#{name}{{
                    background: {bg};
                }}""".format(
                # We style by name, otherwise all inheriting widgets get the same
                # colored background, for example context menu.
                name=background_parent.objectName(),
                bg=background,
            ))

        cf = QTextCharFormat()
        # cf.setFont(f)
        # cf.setForeground(QColor(opt["fontColor"]))

        self.setCursorWidth(opt["cursorWidth"])

        bf = QTextBlockFormat()
        bf.setLineHeight(opt["lineSpacing"], bf.ProportionalHeight)
        bf.setTextIndent(opt["tabWidth"] * 1 if opt["indent"] else 0)
        bf.setTopMargin(opt["spacingAbove"])
        bf.setBottomMargin(opt["spacingBelow"])
        bf.setAlignment(Qt.AlignLeft if opt["textAlignment"] == 0 else
                        Qt.AlignCenter if opt["textAlignment"] == 1 else
                        Qt.AlignRight if opt["textAlignment"] == 2 else
                        Qt.AlignJustify)

        self._defaultCharFormat = cf
        self._defaultBlockFormat = bf

        if self.highlighter:
            self.highlighter.updateColorScheme()
            self.highlighter.setMisspelledColor(QColor(opt["misspelled"]))
            self.highlighter.setDefaultCharFormat(self._defaultCharFormat)
            self.highlighter.setDefaultBlockFormat(self._defaultBlockFormat)

    def update(self, topLeft, bottomRight):
        update = False

        if self._index and self._index.isValid():
            if topLeft.parent() != self._index.parent():
                return

                # LOGGER.debug("Model changed: ({}:{}), ({}:{}/{}), ({}:{}) for {} of {}".format(
                # topLeft.row(), topLeft.column(),
                # self._index.row(), self._index.row(), self._column,
                # bottomRight.row(), bottomRight.column(),
                # self.objectName(), self.parent().objectName()))

            if topLeft.row() <= self._index.row() <= bottomRight.row():
                if topLeft.column() <= self._column <= bottomRight.column():
                    update = True

        elif self._indexes:
            for i in self._indexes:
                if topLeft.row() <= i.row() <= bottomRight.row():
                    update = True

        if update:
            self.updateText()

    def disconnectDocument(self):
        if not self.updateTimerConnection:
            return

        try:
            self.document().contentsChanged.disconnect(self.updateTimerConnection)
            self.updateTimerConnection = None
        except:
            pass

    def reconnectDocument(self):
        if not self.updateTimer or self.updateTimerConnection:
            return

        self.updateTimerConnection = self.document().contentsChanged.connect(self.updateTimer.start, F.AUC)

    def toIdealText(self):
        """The text of this editor's document, NBSP and all.

        The one definition of that, in manuskript.domain.text, so that the
        buffer this editor may be sharing answers identically -- comparing
        two spellings of the same text is how undo history got thrown away
        once already.
        """
        return plain_text(self.document())
    toPlainText = toIdealText

    def updateText(self):
        if self._buffer is not None:
            # The buffer decides. It knows whether what it holds is newer
            # than what the model is offering, which one view cannot know
            # on behalf of the others reading the same text.
            self._buffer.load(F.toString(self._index.data()))
            return

        self._updating.lock()

        # LOGGER.debug("Updating %s", self.objectName())
        if self._index:
            self.disconnectDocument()
            if self.toIdealText() != F.toString(self._index.data()):
                # LOGGER.debug("    Updating plaintext")
                self.document().setPlainText(F.toString(self._index.data()))
            self.reconnectDocument()

        elif self._indexes:
            self.disconnectDocument()
            t = []
            same = True
            for i in self._indexes:
                item = i.internalPointer()
                t.append(F.toString(item.data(self._column)))

            for t2 in t[1:]:
                if t2 != t[0]:
                    same = False
                    break

            if same:
                self.document().setPlainText(t[0])
            else:
                self.document().setPlainText("")

                if not self._placeholderText:
                    self._placeholderText = self.placeholderText()

                self.setPlaceholderText(self.tr("Various"))
            self.reconnectDocument()

        self._updating.unlock()

    def submit(self):
        if self._buffer is not None:
            # One buffer, one write. Every view submitting its own copy of
            # the same text was the duplication in the first place.
            self._buffer.flush()
            return

        if self.updateTimer:
            self.updateTimer.stop()

        self._updating.lock()
        text = self.toIdealText()
        self._updating.unlock()

        # LOGGER.debug("Submitting %s", self.objectName())
        if self._index and self._index.isValid():
            # item = self._index.internalPointer()
            if text != self._index.data():
                # LOGGER.debug("    Submitting plain text")
                self._model.setData(QModelIndex(self._index), text)

        elif self._indexes:
            for i in self._indexes:
                item = i.internalPointer()
                if text != F.toString(item.data(self._column)):
                    LOGGER.debug("Submitting many indexes")
                    self._model.setData(i, text)

    def keyPressEvent(self, event):
        if self._buffer is not None and event.matches(QKeySequence.Undo):
            self._buffer.document.undo()
            event.accept()
            return
        if self._buffer is not None and event.matches(QKeySequence.Redo):
            self._buffer.document.redo()
            event.accept()
            return
        if event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            text = QApplication.clipboard().text()
            self.insertPlainText(text)
        else:
            QTextEdit.keyPressEvent(self, event)

        if event.key() == Qt.Key_Space:
            self.submit()

    def undo(self):
        """Undo text at the shared authority, if this is a shared view."""
        if self._buffer is not None:
            self._buffer.document.undo()
            return
        QTextEdit.undo(self)

    def redo(self):
        """Redo text at the shared authority, if this is a shared view."""
        if self._buffer is not None:
            self._buffer.document.redo()
            return
        QTextEdit.redo(self)

    # -----------------------------------------------------------------------------------------------------
    # Resize stuff

    def resizeEvent(self, e):
        QTextEdit.resizeEvent(self, e)
        if self._autoResize:
            self.sizeChange()

    def sizeChange(self):
        opt = self.settings.textEditor
        docHeight = self.document().size().height() + 2 * opt["marginsTB"]
        if self.heightMin <= docHeight <= self.heightMax:
            self.setMinimumHeight(int(docHeight))

    def setAutoResize(self, val):
        self._autoResize = val
        if self._autoResize:
            self.document().contentsChanged.connect(self.sizeChange)
            self.heightMin = 0
            self.heightMax = 65000
            self.sizeChange()

        ###############################################################################
        # SPELLCHECKING
        ###############################################################################
        # Based on http://john.nachtimwald.com/2009/08/22/qplaintextedit-with-in-line-spell-check/

    def setDict(self, d):
        """Use a dictionary, repainting only if the spelling marks change.

        Rehighlighting walks every block of the document. Opening a project
        sets the dictionary on every editor in the window -- 62 of them, and
        almost always to the dictionary they already had -- so this was 62
        full repaints to arrive at the marks already on screen.
        """
        settled = self.currentDict == d and (not d or self._dict is not None)
        self.currentDict = d
        if d:
            self._dict = Spellchecker.getDictionary(d)
        if settled:
            return
        if self.highlighter:
            self.highlighter.rehighlight()

    def toggleSpellcheck(self, v):
        """Turn spelling marks on or off, repainting only on a change.

        Compared after the fact rather than before, because asking for
        spellcheck without a dictionary does not get it: what decides
        whether anything needs repainting is the state this leaves behind,
        not the state that was requested.
        """
        was_checking = self.spellcheck
        self.spellcheck = v
        if self.spellcheck and not self._dict:
            self._dict = Spellchecker.getDictionary(self.currentDict)

        if not self._dict:
            self.spellcheck = False

        if self.spellcheck == was_checking:
            return

        if self.highlighter:
            self.highlighter.rehighlight()
        else:
            self.spellcheck = False

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # Rewrite the mouse event to a left button event so the cursor is
            # moved to the location of the pointer.
            event = QMouseEvent(QEvent.MouseButtonPress, event.pos(),
                                Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        QTextEdit.mousePressEvent(self, event)
        # A click is itself sufficient evidence that this editor is the
        # workspace command target. Some headless/native Qt backends defer or
        # omit focusChanged even though the text edit receives the press.
        self._reportWorkspaceFocus()

    def beginTooltipMoveEvent(self):
        self._tooltip['depth'] += 1

    def endTooltipMoveEvent(self):
        self._tooltip['depth'] -= 1

    def showTooltip(self, pos, text):
        QToolTip.showText(pos, text)
        self._tooltip['active'] = self._tooltip['depth']

    def hideTooltip(self):
        if self._tooltip['active'] == self._tooltip['depth']:
            QToolTip.hideText()

    def mouseMoveEvent(self, event):
        """
        When mouse moves, we show tooltip when appropriate.
        """
        self.beginTooltipMoveEvent()
        QTextEdit.mouseMoveEvent(self, event)
        self.endTooltipMoveEvent()

        match = None

        # Check if the selected word has any suggestions for correction
        if self.spellcheck and self._dict:
            cursor = self.cursorForPosition(event.pos())

            # Searches for correlating/overlapping matches
            suggestions = self._dict.findSuggestions(self.toPlainText(), cursor.selectionStart(), cursor.selectionEnd())

            if len(suggestions) > 0:
                # I think it should focus on one type of error at a time.
                match = suggestions[0]

        if match:
            # Wrap the message into a fitting width
            msg_lines = textwrap.wrap(match.msg, 48)

            self.showTooltip(event.globalPos(), "\n".join(msg_lines))
        else:
            self.hideTooltip()

    def wheelEvent(self, event):
        """
        We catch wheelEvent if key modifier is CTRL to change font size.
        Note: this should be in a class specific for main textEditView (#TODO).
        """
        if event.modifiers() & Qt.ControlModifier:
            # Get the wheel angle.
            d = event.angleDelta().y() / 120

            # Update settings
            f = QFont()
            f.fromString(self.settings.textEditor["font"])
            f.setPointSizeF(f.pointSizeF() + d)
            self.settings.textEditor["font"] = f.toString()

            if self.text_editor_context is not None:
                self.text_editor_context.reload_fonts()
            else:
                self.loadFontSettings()

            # We tell the world that we accepted this event
            event.accept()
            return

        QTextEdit.wheelEvent(self, event)

    class SpellAction(QAction):
        """A special QAction that returns the text in a signal. Used for spellcheck."""

        correct = pyqtSignal(str)

        def __init__(self, *args):
            QAction.__init__(self, *args)

            self.triggered.connect(lambda x: self.correct.emit(
                str(self.text())))

    def contextMenuEvent(self, event):
        # Based on http://john.nachtimwald.com/2009/08/22/qplaintextedit-with-in-line-spell-check/
        popup_menu = self.createStandardContextMenu()
        popup_menu.exec_(event.globalPos())

    def appendContextMenuEntriesForWord(self, popup_menu, selectedWord):
        # Entity creation belongs to the Markdown-aware editor, which can
        # offer schemas from the canonical catalogue.  A base text widget
        # must never fall back to mutating the hidden legacy story models.
        return popup_menu

    def createStandardContextMenu(self):
        popup_menu = QTextEdit.createStandardContextMenu(self)

        # QTextEdit's standard Undo and Redo actions operate directly on the
        # document installed in the widget. A shared editor's installed
        # document is deliberately only a view-local projection and has no
        # undo stack; history belongs to the buffer's master document. Keep
        # the familiar menu positions while routing the commands correctly.
        if self._buffer is not None:
            actions = popup_menu.actions()
            before = actions[2] if len(actions) > 2 else None
            for action in actions[:2]:
                popup_menu.removeAction(action)
                action.deleteLater()
            undo_action = QAction(self.tr("&Undo"), popup_menu)
            undo_action.setShortcut(QKeySequence.Undo)
            undo_action.setEnabled(self._buffer.document.isUndoAvailable())
            undo_action.triggered.connect(self.undo)
            redo_action = QAction(self.tr("&Redo"), popup_menu)
            redo_action.setShortcut(QKeySequence.Redo)
            redo_action.setEnabled(self._buffer.document.isRedoAvailable())
            redo_action.triggered.connect(self.redo)
            popup_menu.insertAction(before, undo_action)
            popup_menu.insertAction(before, redo_action)

        cursor = self.textCursor()
        selectedWord = cursor.selectedText() if cursor.hasSelection() else None

        if not self.spellcheck:
            return self.appendContextMenuEntriesForWord(popup_menu, selectedWord)

        suggestions = []

        # Check for any suggestions for corrections at the cursors position
        if self._dict is not None:
            text = self.toPlainText()

            suggestions = self._dict.findSuggestions(text, cursor.selectionStart(), cursor.selectionEnd())

            # Select the word under the cursor if necessary.
            # But only if there is no selection (otherwise it's impossible to select more text to copy/cut)
            if not cursor.hasSelection() and len(suggestions) == 0:
                old_position = cursor.position()

                cursor.select(QTextCursor.WordUnderCursor)
                self.setTextCursor(cursor)

                if cursor.hasSelection():
                    selectedWord = cursor.selectedText()

                    # Check if the selected word is misspelled and offer spelling
                    # suggestions if it is.
                    suggestions = self._dict.findSuggestions(text, cursor.selectionStart(), cursor.selectionEnd())

                if len(suggestions) == 0:
                    cursor.clearSelection()
                    cursor.setPosition(old_position, QTextCursor.MoveAnchor)
                    self.setTextCursor(cursor)

                    selectedWord = None

        popup_menu = self.appendContextMenuEntriesForWord(popup_menu, selectedWord)

        if len(suggestions) > 0 or selectedWord is not None:
            valid = len(suggestions) == 0

            if not valid:
                # I think it should focus on one type of error at a time.
                match = suggestions[0]

                popup_menu.insertSeparator(popup_menu.actions()[0])

                if match.locqualityissuetype == 'misspelling':
                    spell_menu = QMenu(self.tr('Spelling Suggestions'), self)
                    spell_menu.setIcon(F.themeIcon("spelling"))

                    if match.end > match.start and selectedWord is None:
                        # Select the actual area of the match
                        cursor = self.textCursor()
                        cursor.setPosition(match.start, QTextCursor.MoveAnchor);
                        cursor.setPosition(match.end, QTextCursor.KeepAnchor);
                        self.setTextCursor(cursor)

                        selectedWord = cursor.selectedText()

                    if match.replacements:
                        for word in match.replacements:
                            action = self.SpellAction(word, spell_menu)
                            action.correct.connect(self.correctWord)
                            spell_menu.addAction(action)

                    # Adds: add to dictionary
                    addAction = QAction(self.tr("&Add to dictionary"), popup_menu)
                    addAction.setIcon(QIcon.fromTheme("list-add"))
                    addAction.triggered.connect(self.addWordToDict)
                    addAction.setData(selectedWord)

                    popup_menu.insertAction(popup_menu.actions()[0], addAction)

                    # Only add the spelling suggests to the menu if there are
                    # suggestions.
                    if match.replacements and len(match.replacements) > 0:
                        # Adds: suggestions
                        popup_menu.insertMenu(popup_menu.actions()[0], spell_menu)
                else:
                    correct_menu = None
                    correct_action = None

                    if len(match.replacements) > 0 and match.end > match.start:
                        # Select the actual area of the match
                        cursor = self.textCursor()
                        cursor.setPosition(match.start, QTextCursor.MoveAnchor);
                        cursor.setPosition(match.end, QTextCursor.KeepAnchor);
                        self.setTextCursor(cursor)

                        if len(match.replacements) > 0:
                            correct_menu = QMenu(self.tr('&Correction Suggestions'), self)
                            correct_menu.setIcon(F.themeIcon("spelling"))

                            for word in match.replacements:
                                action = self.SpellAction(word, correct_menu)
                                action.correct.connect(self.correctWord)
                                correct_menu.addAction(action)

                    if correct_menu is None:
                        correct_action = QAction(self.tr('&Correction Suggestion'), popup_menu)
                        correct_action.setIcon(F.themeIcon("spelling"))
                        correct_action.setEnabled(False)

                    # Wrap the message into a fitting width
                    msg_lines = textwrap.wrap(match.msg, 48)

                    # Insert the lines of the message backwards
                    for i in range(0, len(msg_lines)):
                        popup_menu.insertSection(popup_menu.actions()[0], msg_lines[len(msg_lines) - (i + 1)])

                    if correct_menu is None:
                        popup_menu.insertAction(popup_menu.actions()[0], correct_action)
                    else:
                        popup_menu.insertMenu(popup_menu.actions()[0], correct_menu)

            # If word was added to custom dict, give the possibility to remove it
            elif self._dict.isCustomWord(selectedWord):
                popup_menu.insertSeparator(popup_menu.actions()[0])
                # Adds: remove from dictionary
                rmAction = QAction(
                    self.tr("&Remove from custom dictionary"), popup_menu)
                rmAction.setIcon(QIcon.fromTheme("list-remove"))
                rmAction.triggered.connect(self.rmWordFromDict)
                rmAction.setData(selectedWord)
                popup_menu.insertAction(popup_menu.actions()[0], rmAction)

        return popup_menu

    def correctWord(self, word):
        """
        Replaces the selected text with word.
        """
        cursor = self.textCursor()
        cursor.beginEditBlock()

        cursor.removeSelectedText()
        cursor.insertText(word)

        cursor.endEditBlock()

    def addWordToDict(self):
        word = self.sender().data()
        self._dict.addWord(word)
        self.highlighter.rehighlight()

    def rmWordFromDict(self):
        word = self.sender().data()
        self._dict.removeWord(word)
        self.highlighter.rehighlight()

    ###############################################################################
    # FORMATTING
    ###############################################################################

    def focusInEvent(self, event):
        """Publish this editor as the workspace command target."""
        QTextEdit.focusInEvent(self, event)
        self._reportWorkspaceFocus()

    def _reportWorkspaceFocus(self):
        """Publish this editor through its injected workspace focus port."""
        context = self.text_editor_context
        focus_received = getattr(context, "focus_received", None)
        if callable(focus_received):
            focus_received(self)

    def releaseWorkspaceFocus(self):
        """Stop routing workspace commands here before native teardown."""
        context = self.text_editor_context
        focus_released = getattr(context, "focus_released", None)
        if callable(focus_released):
            focus_released(self)

    def focusOutEvent(self, event):
        """Submit changes just before focusing out."""
        QTextEdit.focusOutEvent(self, event)
        self.submit()

    ###############################################################################
    # KEYBOARD SHORTCUTS
    ###############################################################################

    def invoke_outline_command(self, command):
        """
        The tree view in main window must have same index as the text
        edit that has focus. So we can pass it the call for documents
        edits like: duplicate, move up, etc.
        """
        if (
            self._index
            and self._column == Outline.text
            and self.text_editor_context is not None
        ):
            self.text_editor_context.invoke_outline_command(command)

    def rename(self):
        self.invoke_outline_command(DocumentCommand.RENAME)

    def duplicate(self):
        self.invoke_outline_command(DocumentCommand.DUPLICATE)

    def moveUp(self):
        self.invoke_outline_command(DocumentCommand.MOVE_UP)

    def moveDown(self):
        self.invoke_outline_command(DocumentCommand.MOVE_DOWN)

    def delete(self):
        self.invoke_outline_command(DocumentCommand.DELETE)
