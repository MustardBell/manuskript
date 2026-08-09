import locale
from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QTimer

from manuskript.enums import Outline
from manuskript.functions import appPath
from manuskript.ui.tools.targets_ui import Ui_targets


@dataclass(frozen=True)
class TargetsContext:
    """Project data and workspace session state shown by TargetsDialog."""

    outline: Callable[[], Any]
    writing_session: Any

    @classmethod
    def for_runtime(cls, runtime, writing_session):
        return cls(
            outline=lambda: runtime.models.outline,
            writing_session=writing_session,
        )


class TargetsDialog(QWidget, Ui_targets):

    def __init__(self, context, parent=None):
        QWidget.__init__(self, parent)
        self.context = context
        self.setupUi(self)
        iconPic = appPath("icons/Manuskript/icon-64px.png")
        self.setWindowIcon(QIcon(iconPic))

        self.session_reset.clicked.connect(self.resetSession)
        
        self.tick()

        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(2000)

    def getDraftStats(self):
        item = self.context.outline().rootItem

        wc = item.data(Outline.wordCount)
        goal = item.data(Outline.goal)
        progress = item.data(Outline.goalPercentage)

        return (
            int(wc) if wc != "" else 0,
            int(goal) if goal != "" else 0,
            float(progress) if progress != "" else 0.0
        )

    def resetSession(self):
        wc, _, _ = self.getDraftStats()
        self.context.writing_session.reset(wc)
        self.tick()

    @staticmethod
    def progress_bar_value(value):
        return int(min(max(float(value) * 100, 0), 100))

    def tick(self):
        wc, goal, progress = self.getDraftStats()
        
        self.draft_wc_label.setText(locale.format_string("%d", wc, grouping=True))
        self.draft_goal_label.setText(locale.format_string("%d", goal, grouping=True))
        # limit to 0-100 for display
        self.draft_progress_bar.setValue(self.progress_bar_value(progress))

        session_wc = self.context.writing_session.words_written(wc)

        self.session_wc_label.setText(locale.format_string("%d", session_wc, grouping=True))
        if self.session_target.value() == 0:
            self.session_progress_bar.setValue(0)
        else:
            self.session_progress_bar.setValue(self.progress_bar_value(session_wc / self.session_target.value()))

    def closeEvent(self, event):
        self.timer = None
