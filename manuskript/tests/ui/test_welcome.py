#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Tests for the welcome widget."""


def test_autoLoad(MWNoProject):
    """
    Tests for the welcome widget using MainWindow with no open project.
    """
    MW = MWNoProject
    from PyQt5.QtCore import QSettings

    # Testing when no autoLoad
    QSettings().remove("autoLoad")
    autoLoad, path = MW.welcome.getAutoLoadValues()
    assert type(autoLoad) == bool
    assert autoLoad == False

    for v in [True, False, 42, "42", None, True]:
        MW.welcome.setAutoLoad(v)
        autoLoad, path = MW.welcome.getAutoLoadValues()
        assert type(autoLoad) == bool


def test_recent_project_is_not_loaded_when_close_is_cancelled(MW):
    from unittest.mock import MagicMock, patch

    action = MagicMock()
    action.data.return_value = "/tmp/next-project.msk"

    with patch.object(MW.welcome, "sender", return_value=action), \
         patch.object(MW.projectManager, "closeProject", return_value=False), \
         patch.object(MW.welcome, "appendToRecentFiles") as append_recent, \
         patch.object(MW.projectManager, "loadProject") as load_project:
        MW.welcome.loadRecentFile()

    append_recent.assert_not_called()
    load_project.assert_not_called()


def test_welcome_dependencies_are_assigned_by_main_window(MW):
    assert MW.welcome.context.project_manager is MW.projectManager
    assert MW.welcome.context.recent_menu is MW.menuRecents


def test_auto_load_project_is_consumed_once(MW):
    MW._autoLoadProject = "/tmp/project.msk"

    assert (
        MW.welcome.context.consume_auto_load_project()
        == "/tmp/project.msk"
    )
    assert MW.welcome.context.consume_auto_load_project() is None
