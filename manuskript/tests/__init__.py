#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Test application composition, created only by tests that need it."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt5 import QtCore
from PyQt5.QtCore import Qt
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
_NativeQSettings = QtCore.QSettings
_NativeQSettings.setDefaultFormat(_NativeQSettings.IniFormat)
for _settings_format in (
    _NativeQSettings.NativeFormat,
    _NativeQSettings.IniFormat,
):
    for _settings_scope in (
        _NativeQSettings.UserScope,
        _NativeQSettings.SystemScope,
    ):
        _NativeQSettings.setPath(
            _settings_format,
            _settings_scope,
            str(_settings_root),
        )


class _PrivateQSettings(_NativeQSettings):
    """Keep implicit application settings out of the host profile.

    Qt's organization/application constructors always select NativeFormat;
    they explicitly ignore ``setDefaultFormat``. Native ``setPath`` is also
    ignored by the plist and registry backends on macOS and Windows. Tests
    import QSettings from QtCore throughout the suite, so replace that Python
    entry point before any test module or application module is imported.

    Explicit filename/format construction remains untouched. It is used by
    migration and repository tests whose files already live below tmp_path.
    """

    def __init__(self, *args):
        args = self._private_arguments(args)
        super().__init__(*args)

    @classmethod
    def _private_arguments(cls, args):
        # QSettings(organization, application[, parent]) always means native
        # storage. Spell out the relocatable INI overload instead.
        if (
            len(args) in (2, 3)
            and isinstance(args[0], str)
            and isinstance(args[1], str)
        ):
            organization, application = args[:2]
            parent = args[2:]
            return (
                cls.IniFormat,
                cls.UserScope,
                organization,
                application,
                *parent,
            )

        # QSettings(scope, organization, application[, parent]) is native too.
        if (
            len(args) in (3, 4)
            and not isinstance(args[0], str)
            and isinstance(args[1], str)
            and isinstance(args[2], str)
        ):
            scope, organization, application = args[:3]
            parent = args[3:]
            return (
                cls.IniFormat,
                scope,
                organization,
                application,
                *parent,
            )

        # Even an explicitly requested native organization store must remain
        # private in a test process. Filename/format overloads do not match.
        if (
            len(args) in (4, 5)
            and not isinstance(args[0], str)
            and not isinstance(args[1], str)
            and isinstance(args[2], str)
            and isinstance(args[3], str)
        ):
            return (cls.IniFormat, *args[1:])

        return args


# Package import precedes collection of every ``manuskript.tests.*`` module,
# and production modules are composed lazily below. Their ordinary
# ``from PyQt5.QtCore import QSettings`` imports therefore receive the guard.
QtCore.QSettings = _PrivateQSettings
QSettings = _PrivateQSettings

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
