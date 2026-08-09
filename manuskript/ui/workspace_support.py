"""Support and diagnostic commands for one workspace."""

import os
from dataclasses import dataclass
from typing import Callable

from PyQt5.QtWidgets import QMessageBox

from manuskript.functions import openURL, showInFolder
from manuskript.logging import getLogFilePath


SUPPORT_URL = (
    "https://github.com/olivierkes/manuskript/wiki/Technical-Support"
)


@dataclass(frozen=True)
class WorkspaceSupportViews:
    translate: Callable[[str], str]
    show_information: Callable[[str, str], bool]
    show_critical: Callable[[str, str], None]
    open_url: Callable[[str], None] = openURL
    log_path: Callable[[], str] = getLogFilePath
    show_file: Callable[[str], bool] = showInFolder

    @classmethod
    def for_window(cls, window):
        parent = window.centralWidget() or window

        def show_information(title, message):
            result = QMessageBox(
                QMessageBox.Information,
                title,
                message,
                QMessageBox.Ok,
                parent,
            ).exec()
            return result == QMessageBox.Ok

        def show_critical(title, message):
            QMessageBox(
                QMessageBox.Critical,
                title,
                message,
                QMessageBox.Ok,
                parent,
            ).exec()

        return cls(
            translate=window.tr,
            show_information=show_information,
            show_critical=show_critical,
        )


class WorkspaceSupportController:
    def __init__(self, views):
        self._views = views

    def open_support(self, _checked=False):
        self._views.open_url(SUPPORT_URL)

    def locate_log(self, _checked=False):
        views = self._views
        translate = views.translate
        logfile = views.log_path()
        if not logfile:
            views.show_information(
                translate("Sorry!"),
                "<p><b>"
                + translate("This session is not being logged.")
                + "</b></p>",
            )
            return

        should_open = views.show_information(
            translate("A log file is a Work in Progress!"),
            "<p><b>"
            + translate(
                'The log file "{}" will continue to be written to until '
                "Manuskript is closed."
            ).format(os.path.basename(logfile))
            + "</b></p><p>"
            + translate(
                "It will now be displayed in your file manager, but is "
                "of limited use until you close Manuskript."
            )
            + "</p>",
        )
        if should_open and not views.show_file(logfile):
            views.show_critical(
                translate("Error!"),
                "<p><b>"
                + translate(
                    "An error was encountered while trying to show the "
                    "log file below in your file manager."
                )
                + "</b></p><p>"
                + logfile
                + "</p>",
            )

    def dispose(self):
        self._views = None
