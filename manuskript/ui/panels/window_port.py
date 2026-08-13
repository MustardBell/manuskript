"""The small set of window operations needed to host panels.

Only :meth:`PanelWindow.for_window` knows these operations come from a
``QMainWindow``.  Panel hosting, mounting, visibility, and failure reporting
receive this port and cannot discover unrelated application or project state.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from PyQt5 import sip
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAction, QDockWidget, QSplitter, QTabBar

from manuskript.ui.panels.failures import PanelFailureReporter


@dataclass(frozen=True)
class PanelWindow:
    """Low-level capabilities required by the panel infrastructure."""

    find_splitter: Callable[[str], Optional[Any]]
    create_dock: Callable[[str], Any]
    restore_dock: Callable[[Any], bool]
    add_dock: Callable[[Any, Any], None]
    remove_dock: Callable[[Any], None]
    activate_dock: Callable[[Any], None]
    create_action: Callable[[str], Any]
    park_widget: Callable[[Any], None]
    failures: Any

    @classmethod
    def for_window(cls, window):
        """Inventory panel capabilities without retaining the catalog."""

        # Splitter slots are part of the composed window, not a dynamic
        # discovery service. Resolve them once while the native tree is known
        # to be intact. Re-entering QObject.findChild during later panel
        # reparenting/deferred deletion made panel construction depend on Qt's
        # native destruction timing and could crash inside SIP without a
        # Python exception.
        splitters = {
            splitter.objectName(): splitter
            for splitter in window.findChildren(QSplitter)
            if splitter.objectName()
        }

        def find_splitter(name):
            return splitters.get(name)

        def create_dock(title):
            dock = QDockWidget(window.tr(title), window)
            dock.setFeatures(
                QDockWidget.DockWidgetClosable
                | QDockWidget.DockWidgetMovable
                | QDockWidget.DockWidgetFloatable
            )
            dock.setAllowedAreas(Qt.AllDockWidgetAreas)
            return dock

        def create_action(title):
            return QAction(window.tr(title), window)

        def park_widget(widget):
            widget.setParent(window)

        def activate_dock(dock):
            """Select a dock even when it is behind a native dock tab.

            QMainWindow exposes which docks are tabified and emits a signal
            after a tab is selected, but Qt 5 has no public method that
            selects one. ``QWidget.raise_()`` does not do so reliably (Qt
            5.15 leaves the old tab in front). The private QTabBar stores each
            QDockWidget's native address as its tab data, so contain that
            version-specific bridge here and retain ``raise_`` as the safe
            fallback. A future Qt/ADS host replaces this one adapter rather
            than teaching panels about QMainWindow internals.
            """
            dock.show()
            if window.tabifiedDockWidgets(dock):
                address = sip.unwrapinstance(dock)
                for tab_bar in window.findChildren(QTabBar):
                    for index in range(tab_bar.count()):
                        try:
                            matches = int(tab_bar.tabData(index)) == address
                        except (TypeError, ValueError):
                            matches = False
                        if matches:
                            tab_bar.setCurrentIndex(index)
                            dock.raise_()
                            return
            dock.raise_()

        presenter = getattr(window, "statusPresenter", None)
        show_status = (
            presenter.show if presenter is not None else None
        )
        return cls(
            find_splitter=find_splitter,
            create_dock=create_dock,
            restore_dock=window.restoreDockWidget,
            add_dock=window.addDockWidget,
            remove_dock=window.removeDockWidget,
            activate_dock=activate_dock,
            create_action=create_action,
            park_widget=park_widget,
            failures=PanelFailureReporter(
                window.tr,
                show_status,
            ),
        )
