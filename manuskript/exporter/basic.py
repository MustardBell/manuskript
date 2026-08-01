#!/usr/bin/env python
# --!-- coding: utf8 --!--
import os
import shutil
import subprocess

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QWidget

import logging
LOGGER = logging.getLogger(__name__)

class basicExporter:

    name = ""
    description = ""
    exportTo = []
    cmd = ""
    customPath = ""
    icon = ""
    absentTip = ""  # A tip displayed when exporter is absent.
    absentURL = ""  # URL to open if exporter is absent.

    def __init__(self, context=None):
        self.context = context
        settings = QSettings()
        self.customPath = settings.value("Exporters/{}_customPath".format(self.name), "")

    def setCustomPath(self, path):
        self.customPath = path
        settings = QSettings()
        settings.setValue("Exporters/{}_customPath".format(self.name), self.customPath)

    def getFormatByName(self, name):
        for f in self.exportTo:
            if f.name == name:
                return f

        return None

    def isValid(self):
        if self.path() != None:
            return 2
        elif self.customPath and os.path.exists(self.customPath):
            return 1
        else:
            return 0

    def version(self):
        return ""

    def path(self):
        return shutil.which(self.cmd)

    def run(self, args):
        if self.isValid() == 2:
            run = self.cmd
        elif self.isValid() == 1:
            run = self.customPath
        else:
            LOGGER.error("No command for %s.", self.name)
            return None
        r = subprocess.check_output([run] + args)  # timeout=.2
        return r.decode("utf-8")

        # Example of how to run a command
        #
        # cmdl = ['txt2tags', '-t', target, '--enc=utf-8', '--no-headers', '-o', '-', '-']
        #
        # cmd = subprocess.Popen(('echo', text), stdout=subprocess.PIPE)
        # try:
        #     output = subprocess.check_output(cmdl, stdin=cmd.stdout, stderr=subprocess.STDOUT)  # , cwd="/tmp"
        # except subprocess.CalledProcessError as e:
        #     LOGGER.error("Failed to read from process output.")
        #     return text
        # cmd.wait()
        #
        # return output.decode("utf-8")


class basicFormat:

    implemented = False
    InvalidBecause = ""
    requires = {
        "Settings": False,
        "Preview": False,
    }
    icon = ""

    def __init__(
        self,
        name=None,
        description=None,
        icon=None,
        context=None,
    ):
        self.context = context
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if icon is not None:
            self.icon = icon

    def settingsWidget(self):
        return QWidget()

    def previewWidget(self):
        return QWidget()

    def preview(self, settingsWidget, previewWidget):
        pass

    def export(self, settingsWidget):
        pass

    def shortcodes(self):
        return [
            ("\n", "\\n")
        ]

    def escapes(self, text):
        for A, B in self.shortcodes():
            text = text.replace(A, B)
        return text

    def descapes(self, text):
        """How do we call that?"""
        for A, B in self.shortcodes():
            text = text.replace(B, A)
        return text

    def isValid(self):
        return True

    def projectPath(self):
        if self.context is None:
            raise RuntimeError("Export context has not been configured.")
        return self.context.project_path
