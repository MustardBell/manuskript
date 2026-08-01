from PyQt5.QtCore import QEvent, QObject
from PyQt5.QtWidgets import QMenu, QToolTip


class MenuTooltipController(QObject):
    """Expose QAction tooltips consistently in menus and the menu bar."""

    def __init__(self, menu_bar, descriptions=None, parent=None):
        super().__init__(parent or menu_bar)
        self._menuBar = menu_bar
        self._menuBar.installEventFilter(self)
        self.refresh(descriptions or {})

    def refresh(self, descriptions=None):
        """Enable menu tooltips after static and dynamic menus are built."""
        for menu in self._menuBar.findChildren(QMenu):
            menu.setToolTipsVisible(True)
            for action in menu.actions():
                if action.statusTip():
                    action.setToolTip(action.statusTip())

        for menu, tooltip in (descriptions or {}).items():
            menu.menuAction().setToolTip(tooltip)

    def eventFilter(self, watched, event):
        if (
            watched is self._menuBar
            and event.type() == QEvent.ToolTip
        ):
            action = self._menuBar.actionAt(event.pos())
            if action is not None and action.toolTip():
                QToolTip.showText(
                    event.globalPos(),
                    action.toolTip(),
                    self._menuBar,
                    self._menuBar.actionGeometry(action),
                )
            else:
                QToolTip.hideText()
            return True

        return QObject.eventFilter(self, watched, event)
