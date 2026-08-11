"""The small set of window operations needed to host panels.

Only :meth:`PanelWindow.for_window` knows these operations come from a
``QMainWindow``.  Panel hosting, mounting, visibility, and failure reporting
receive this port and cannot discover unrelated application or project state.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from PyQt5.QtWidgets import QAction, QDockWidget, QSplitter

from manuskript.ui.panels.failures import PanelFailureReporter


@dataclass(frozen=True)
class PanelWindow:
    """Low-level capabilities required by the panel infrastructure."""

    find_splitter: Callable[[str], Optional[Any]]
    create_dock: Callable[[str], Any]
    restore_dock: Callable[[Any], bool]
    add_dock: Callable[[Any, Any], None]
    remove_dock: Callable[[Any], None]
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
            return QDockWidget(window.tr(title), window)

        def create_action(title):
            return QAction(window.tr(title), window)

        def park_widget(widget):
            widget.setParent(window)

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
            create_action=create_action,
            park_widget=park_widget,
            failures=PanelFailureReporter(
                window.tr,
                show_status,
            ),
        )
