#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Test application composition, created only by tests that need it."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QApplication


# Every pytest process gets a settings filesystem of its own.  Process-level
# Qt isolation is incomplete if QSettings still joins the processes through a
# developer's real profile (or through one shared CI runner profile): a closed
# ``window-2`` from one batch can otherwise become the layout of a fresh
# transfer wrapper in another.  INI format makes the location override work
# consistently on Linux, macOS, and Windows instead of falling through to the
# registry or platform preferences service.
_settings_directory = TemporaryDirectory(prefix="manuskript-tests-")
_settings_root = Path(_settings_directory.name)
QSettings.setDefaultFormat(QSettings.IniFormat)
for _settings_format in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(
        _settings_format,
        QSettings.UserScope,
        str(_settings_root),
    )

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

    from manuskript import main

    test_settings = QSettings(
        "manuskript_tests", "manuskript_tests",
    )
    test_settings.remove("workspace/openWindows")
    # Production composes the primary window from saved surface membership.
    # Focused tests require their shared primary to begin canonical even if a
    # previous interrupted test process left a sparse membership behind.
    test_settings.remove("workspace/windows/main/surfaces")
    arguments = main.process_commandline([])
    _application = main.prepare(arguments, tests=True)
    return _application
