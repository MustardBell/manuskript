#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QToolBar, QDockWidget, QAction, QToolButton, QSizePolicy, QStylePainter, \
    QStyleOptionButton, QStyle

from manuskript.ui import style


class collapsibleDockWidgets(QToolBar):
    """
    QMainWindow "mixin" which provides auto-hiding support for dock widgets
    (not toolbars).
    """
    TRANSPOSED_AREA = {
        Qt.LeftDockWidgetArea: Qt.LeftToolBarArea,
        Qt.RightDockWidgetArea: Qt.RightToolBarArea,
        Qt.TopDockWidgetArea: Qt.TopToolBarArea,
        Qt.BottomDockWidgetArea: Qt.BottomToolBarArea,
    }

    def __init__(self, area, parent, name=""):
        QToolBar.__init__(self, parent)
        self._area = area
        if not name:
            name = self.tr("Dock Widgets Toolbar")
        self.setObjectName(name)
        self.setWindowTitle(name)

        self.setFloatable(False)
        self.setMovable(False)

        # self.setAllowedAreas(self.TRANSPOSED_AREA[self._area])
        self.parent().addToolBar(self.TRANSPOSED_AREA[self._area], self)

        self._dockToButtonAction = {}

        # Dock widgets
        for d in self._dockWidgets():
            b = verticalButton(self)
            b.setDefaultAction(d.toggleViewAction())
            # d.setStyleSheet("QDockWidget::title{background-color: red;}")
            # d.setTitleBarWidget(QLabel(d.windowTitle()))
            d.setStyleSheet(style.dockSS())
            a = self.addWidget(b)
            self._dockToButtonAction[d] = a

        self.addSeparator()

        # Other widgets
        self.otherWidgets = []
        #: Panel id -> its toolbar entry, so a panel that moves to
        #: another window can take its button away with it.
        self._panelToggles = {}
        self.currentGroup = None

        self.setStyleSheet(style.toolBarSS())
        self.layout().setContentsMargins(0,0,0,0)

    def _dockWidgets(self):
        mw = self.parent()
        for w in mw.findChildren(QDockWidget, None):
            yield w

    def addCustomWidget(self, text, widget, group=None, defaultVisibility=True):
        """
        Adds a custom widget to the toolbar.

        Kept for widgets that own nothing but their toggle. Panels have
        their action made by the panel host; use `addPanelToggle` for
        those so every button mirrors the one action.

        `text` is the name that will displayed on the button to switch visibility.
        `widget` is the widget to control from the toolbar.
        `group` is a compatibility hook for older extensions. Core panels do
            not use it because several independent surfaces may be visible.
        `defaultVisibility` is the default visibility of the item when it is added.
            This allows for the widget to be added to `collapsibleDockWidgets` after
            they've been created but before they are shown, and yet specify their
            desired visibility. Otherwise it creates troubles, see #167 on github:
            https://github.com/olivierkes/manuskript/issues/167.
        """
        a = QAction(text, self)
        a.setCheckable(True)
        a.setChecked(defaultVisibility)
        a.toggled.connect(widget.setVisible)
        widget.setVisible(defaultVisibility)
        # widget.installEventFilter(self)
        b = verticalButton(self)
        b.setDefaultAction(a)
        #b.setChecked(widget.isVisible())
        a2 = self.addWidget(b)
        self.otherWidgets.append((b, a2, widget, group))

    def addPanelToggle(self, action, widget, group=None, panel_id=None):
        """Show a panel's own toggle action as a vertical button.

        The action already controls the widget's visibility; the button
        only mirrors it, so toggling from anywhere keeps every view of
        the panel's state in agreement.
        """
        b = verticalButton(self)
        b.setDefaultAction(action)
        entry = self.addWidget(b)
        self.otherWidgets.append((b, entry, widget, group))
        if panel_id is not None:
            self._panelToggles[panel_id] = (b, entry, widget, group)
        if group is not None and self.currentGroup is not None:
            entry.setVisible(group == self.currentGroup)

    def removePanelToggle(self, panel_id):
        """Take away the button for a panel this window no longer has."""
        found = self._panelToggles.pop(panel_id, None)
        if found is None:
            return
        button, entry, _widget, _group = found
        if found in self.otherWidgets:
            self.otherWidgets.remove(found)
        self.removeAction(entry)
        button.setParent(None)
        button.deleteLater()

        # def eventFilter(self, widget, event):
        # if event.type() in [QEvent.Show, QEvent.Hide]:
        # for btn, action, w, grp in self.otherWidgets:
        # if w == widget:
        # btn.defaultAction().setChecked(event.type() == QEvent.Show)
        # return False

    def switchActionByWidget(self, widget, visibility=True):
        for _btn, _action, _widget, _grp in self.otherWidgets:
            if widget == _widget:
                _btn.setChecked(visibility)

    def setCurrentGroup(self, group):
        """Show this legacy group's buttons, and every independent panel.

        A toggle without a group is one the whole window offers -- the
        entity docks describe the project rather than any single main
        tab -- so a tab change must leave it reachable.
        """
        self.currentGroup = group
        for btn, action, widget, grp in self.otherWidgets:
            action.setVisible(grp is None or grp == group)

    def setDockVisibility(self, dock, val):
        dock.setVisible(val)
        self._dockToButtonAction[dock].setVisible(val)

    def saveState(self):
        """
        Saves and returns the state of the custom widgets. The visibility of the
        docks is not saved since it is included in `QMainWindow.saveState`.
        """
        state = []
        for btn, act, w, grp in self.otherWidgets:
            state.append(
                (grp, btn.text(), btn.isChecked())
            )
        return state

    def restoreState(self, state):
        """Restores the state of the custom widgets."""
        for group, title, status in state:
            for btn, act, widget, grp in self.otherWidgets:
                # Strip '&' from both title and btn.text() to improve matching because
                #   title contains "&" shortcut character whereas btn.text() does not.
                if group == grp and title.replace('&', '') == btn.text().replace('&', ''):
                    btn.setChecked(status)
                    btn.defaultAction().setChecked(status)
                    widget.setVisible(status)


class verticalButton(QToolButton):
    def __init__(self, parent):
        QToolButton.__init__(self, parent)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

        self.setStyleSheet(style.verticalToolButtonSS())

    def sizeHint(self):
        return QToolButton.sizeHint(self).transposed()

    def paintEvent(self, event):
        p = QStylePainter(self)
        p.rotate(90)
        p.translate(0, - self.width())
        opt = QStyleOptionButton()
        opt.initFrom(self)
        opt.text = self.text()
        if self.isChecked():
            opt.state |= QStyle.State_On
        s = opt.rect.size().transposed()
        opt.rect.setSize(s)
        p.drawControl(QStyle.CE_PushButton, opt)
