#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Test application composition, created only by tests that need it."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

# Widgets constructed by focused UI tests still need an application. Own
# exactly one for the interpreter lifetime, as Qt requires, while deferring
# the expensive main window and project composition until a workspace fixture
# is requested. The old CI workaround constructed and immediately destroyed
# an anonymous QApplication before this one; modern Qt retains process-global
# GUI state across that destruction, making every later widget undefined.
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
app = QApplication([])

_application = None


def prepare_test_application():
    """Build the session's QApplication and primary workspace lazily.

    Importing a test package must not construct the entire GUI for more
    than a thousand domain and service tests. Qt tests request the ``MW``
    fixture, which comes through here and shares one deliberately composed
    application for the session.
    """
    global _application
    if _application is not None:
        return _application

    from PyQt5.QtCore import QSettings
    from manuskript import main

    QSettings(
        "manuskript_tests", "manuskript_tests",
    ).remove("workspace/openWindows")
    arguments = main.process_commandline([])
    _application = main.prepare(arguments, tests=True)
    return _application
