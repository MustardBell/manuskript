#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QMouseEvent, QFont
from PyQt5.QtWidgets import (
    QFrame,
    QLineEdit,
    QPlainTextEdit,
    QStyledItemDelegate,
)

from manuskript.enums import Outline
from manuskript.ui.views.cards import CardContext, PlainCardStyle
from manuskript.ui.views.outline_colors import OutlineColorResolver


class corkDelegate(QStyledItemDelegate):
    def __init__(
            self, parent=None, status_model=None, color_resolver=None,
            settings=None):
        QStyledItemDelegate.__init__(self, parent)
        self.status_model = status_model
        self.color_resolver = color_resolver or OutlineColorResolver()
        self.settings = settings
        self.factor = (
            settings.corkSizeFactor / 100.
            if settings is not None
            else 1.
        )
        self.lastPos = None
        self.editing = None
        self.margin = 5
        self.style = PlainCardStyle()
        self._layout = None

        self.bgColors = {}

    def set_status_model(self, status_model):
        self.status_model = status_model

    def set_color_resolver(self, color_resolver):
        self.color_resolver = color_resolver or OutlineColorResolver()

    def set_settings(self, settings):
        if settings is not None:
            self.settings = settings
            self.factor = settings.corkSizeFactor / 100.

    def status_item(self, status):
        if self.status_model is None:
            return None
        return self.status_model.item(int(status), 0)

    def set_style(self, style):
        if style is not None:
            self.style = style

    def setCorkSizeFactor(self, v):
        self.factor = v / 100.

    def sizeHint(self, option, index):
        return self.style.size_hint(self.factor)

    def editorEvent(self, event, model, option, index):
        # We catch the mouse position in the widget to know which part to edit
        if type(event) == QMouseEvent:
            self.lastPos = event.pos()  # - option.rect.topLeft()
        return QStyledItemDelegate.editorEvent(self, event, model, option, index)

    def createEditor(self, parent, option, index):
        # When the user performs a global search and selects an Outline result (title or summary), the
        # associated chapter is selected in cork view, triggering a call to this method with the results
        # list widget set in self.sender(). In this case we store the searched column so we know which
        # editor should be created.
        searchedColumn = None
        if self.sender() is not None and self.sender().objectName() == 'result' and self.sender().currentItem():
            searchedColumn = self.sender().currentItem().data(Qt.UserRole).column()

        self.updateRects(option, index)

        bgColor = self.bgColors.get(index, "white")

        if searchedColumn == Outline.summarySentence or (self.lastPos is not None and self._layout.main_line.contains(self.lastPos)):
            # One line summary
            self.editing = Outline.summarySentence
            edt = QLineEdit(parent)
            edt.setFocusPolicy(Qt.StrongFocus)
            edt.setFrame(False)
            self.style.configure_editor(
                edt, Outline.summarySentence, QFont(option.font))
            edt.setPlaceholderText(self.tr("One line summary"))
            edt.setStyleSheet("background: {}; color: black;".format(bgColor))
            return edt

        elif searchedColumn == Outline.title or (self.lastPos is not None and self._layout.title.contains(self.lastPos)):
            # Title
            self.editing = Outline.title
            edt = QLineEdit(parent)
            edt.setFocusPolicy(Qt.StrongFocus)
            edt.setFrame(False)
            self.style.configure_editor(
                edt, Outline.title, QFont(option.font))
            edt.setStyleSheet("background: {}; color: black;".format(bgColor))
            return edt

        else:  # the full summary fills whatever is left
            # Summary
            self.editing = Outline.summaryFull
            edt = QPlainTextEdit(parent)
            edt.setFocusPolicy(Qt.StrongFocus)
            edt.setFrameShape(QFrame.NoFrame)
            try:
                # QPlainTextEdit.setPlaceholderText was introduced in Qt 5.3
                edt.setPlaceholderText(self.tr("Full summary"))
            except AttributeError:
                pass
            edt.setStyleSheet("background: {}; color: black;".format(bgColor))
            return edt

    def updateEditorGeometry(self, editor, option, index):

        if self.editing == Outline.summarySentence:
            # One line summary
            editor.setGeometry(self._layout.main_line)

        elif self.editing == Outline.title:
            # Title
            editor.setGeometry(self._layout.title)

        elif self.editing == Outline.summaryFull:
            # Summary
            editor.setGeometry(self._layout.main_text)

    def setEditorData(self, editor, index):
        item = index.internalPointer()

        if self.editing == Outline.summarySentence:
            # One line summary
            editor.setText(item.data(Outline.summarySentence))

        elif self.editing == Outline.title:
            # Title
            editor.setText(index.data())

        elif self.editing == Outline.summaryFull:
            # Summary
            editor.setPlainText(item.data(Outline.summaryFull))

    def setModelData(self, editor, model, index):

        if self.editing == Outline.summarySentence:
            # One line summary
            model.setData(index.sibling(index.row(), Outline.summarySentence), editor.text())

        elif self.editing == Outline.title:
            # Title
            model.setData(index, editor.text(), Outline.title)

        elif self.editing == Outline.summaryFull:
            # Summary
            model.setData(index.sibling(index.row(), Outline.summaryFull), editor.toPlainText())

    def cardContext(self, option, index):
        item = index.internalPointer()
        return CardContext(
            index=index,
            option=option,
            item=item,
            colors=self.color_resolver.colors_for(item),
            settings=self.settings,
            factor=self.factor,
            margin=self.margin,
            status_item=self.status_item,
            bg_colors=self.bgColors,
        )

    def updateRects(self, option, index):
        """Recompute the current card's geometry through the active style."""
        self._layout = self.style.layout(self.cardContext(option, index))
        return self._layout



    def paint(self, p, option, index):
        if not index.isValid():
            return
        ctx = self.cardContext(option, index)
        self._layout = self.style.layout(ctx)
        self.style.paint(p, ctx, self._layout)
