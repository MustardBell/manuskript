#!/usr/bin/env python
# --!-- coding: utf8 --!--
import os
import shutil
import subprocess

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import qApp
from PyQt5.QtGui import QCursor

from manuskript.converters.abstractConverter import abstractConverter
from manuskript.services.external_tools import ExternalToolPaths

import logging
LOGGER = logging.getLogger(__name__)

class pandocConverter(abstractConverter):

    name = "pandoc"
    cmd = "pandoc"

    @classmethod
    def isValid(cls, tool_paths=None):
        if cls.path() is not None:
            return 2
        custom_path = cls.customPath(tool_paths)
        if custom_path and os.path.exists(custom_path):
            return 1
        return 0

    @classmethod
    def customPath(cls, tool_paths=None):
        paths = tool_paths or ExternalToolPaths()
        return paths.get(cls.name)

    @classmethod
    def path(cls):
        return shutil.which(cls.cmd)

    @classmethod
    def convert(
            cls, src, _from="markdown", to="html", args=None,
            outputfile=None, on_error=None, tool_paths=None):
        if not cls.isValid(tool_paths):
            LOGGER.error("pandocConverter is called but not valid.")
            return ""

        cmd = [cls.runCmd(tool_paths)]

        cmd += ["--from={}".format(_from)]
        cmd += ["--to={}".format(to)]

        if args:
            cmd += args

        if outputfile:
            cmd.append("--output={}".format(outputfile))

        qApp.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            if not isinstance(src, bytes):
                src = src.encode("utf-8")

            stdout, stderr = process.communicate(src)
        finally:
            qApp.restoreOverrideCursor()

        if stderr:
            err = stderr.decode("utf-8", errors="replace")
            LOGGER.error(err)
            if on_error is not None:
                on_error(err)
            return None

        return stdout.decode("utf-8")

    @classmethod
    def runCmd(cls, tool_paths=None):
        validity = cls.isValid(tool_paths)
        if validity == 2:
            return cls.cmd
        if validity == 1:
            return cls.customPath(tool_paths)
        return None
