from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtCore import QTimer

from manuskript.ui import style


@dataclass(frozen=True)
class StatusPresenterViews:
    """The label and geometry operations needed to present a status."""

    label: Any
    hide_native_status: Callable[[], None]
    layout_spacing: Callable[[], int]
    local_bottom: Callable[[], int]

    @classmethod
    def for_window(cls, window, label):
        return cls(
            label=label,
            hide_native_status=lambda: window.statusBar().hide(),
            layout_spacing=lambda: window.layout().spacing(),
            local_bottom=lambda: window.mapFromGlobal(
                window.geometry().bottomLeft()
            ).y(),
        )


class StatusPresenter:
    """Render application status messages in the main-window overlay."""

    def __init__(self, views):
        self.views = views
        self.label = views.label

    def show(self, message, duration=5000, importance=1):
        self.views.hide_native_status()
        self.label.setText(message)

        styles = {
            0: "color:{};".format(style.textLighter),
            1: "color:{};".format(style.textLight),
            2: "color:{}; font-weight: bold;".format(style.text),
            3: "color:red; font-weight: bold;",
        }
        self.label.setStyleSheet(styles.get(importance, styles[1]))
        self.label.adjustSize()

        geometry = self.label.geometry()
        spacing = int(self.views.layout_spacing() / 2)
        geometry.setLeft(spacing)
        geometry.moveBottom(
            self.views.local_bottom() - spacing
        )
        self.label.setGeometry(geometry)
        self.label.show()
        QTimer.singleShot(duration, self.label.hide)

    def dispose(self):
        self.views = None
        self.label = None
