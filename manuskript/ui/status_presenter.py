from PyQt5.QtCore import QTimer

from manuskript.ui import style


class StatusPresenter:
    """Render application status messages in the main-window overlay."""

    def __init__(self, window, label):
        self.window = window
        self.label = label

    def show(self, message, duration=5000, importance=1):
        self.window.statusBar().hide()
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
        spacing = int(self.window.layout().spacing() / 2)
        geometry.setLeft(spacing)
        geometry.moveBottom(
            self.window.mapFromGlobal(
                self.window.geometry().bottomLeft()
            ).y() - spacing
        )
        self.label.setGeometry(geometry)
        self.label.show()
        QTimer.singleShot(duration, self.label.hide)
