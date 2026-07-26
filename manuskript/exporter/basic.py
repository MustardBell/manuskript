#!/usr/bin/env python
# --!-- coding: utf8 --!--
from PyQt5.QtWidgets import QWidget

from manuskript.services.external_tools import ExternalTool

import logging
LOGGER = logging.getLogger(__name__)

class basicExporter:

    name = ""
    description = ""
    exportTo = []
    cmd = ""
    icon = ""
    absentTip = ""  # A tip displayed when exporter is absent.
    absentURL = ""  # URL to open if exporter is absent.

    def __init__(self, context=None):
        self.context = context
        paths = (
            context.tool_paths
            if context is not None
            else None
        )
        self.tool = ExternalTool(
            self.cmd or self.name,
            self.cmd,
            paths=paths,
        )

    @property
    def customPath(self):
        return self.tool.custom_path

    def setCustomPath(self, path):
        self.tool.custom_path = path

    def getFormatByName(self, name):
        for f in self.exportTo:
            if f.name == name:
                return f

        return None

    def isValid(self):
        return self.tool.availability

    def version(self):
        return ""

    def path(self):
        return self.tool.system_path

    def executable(self):
        availability = self.isValid()
        if availability == 2:
            return self.cmd
        if availability == 1:
            return self.customPath
        return None

    def run(self, args):
        result = self.tool.run_text(
            args,
            executable=self.executable(),
        )
        if result is None:
            LOGGER.error("No command for %s.", self.name)
        return result

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
