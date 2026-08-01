#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Tests."""

# METHOD 1
# ========
# Don't know why, this causes seg fault on SemaphoreCI
# Seg fault in app = QApplication(...)
# Workaround: create and discard an app first...
from PyQt5.QtWidgets import QApplication
QApplication([])

# Create app and mainWindow
from manuskript import main
arguments = main.process_commandline([])
app, MW = main.prepare(arguments, tests=True)

# METHOD 2
# ========
# We need a qApplication to be running, or all the calls to qApp
# will throw a seg fault.
# from PyQt5.QtWidgets import QApplication
# app = QApplication([])
# app.setOrganizationName("manuskript_tests")
# app.setApplicationName("manuskript_tests")

# from manuskript.mainWindow import MainWindow
# MW = MainWindow()
