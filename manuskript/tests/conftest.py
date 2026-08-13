#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Fixtures."""

import os

import pytest


def closeProjectDiscardingChanges(MW):
    """Close a test project without persisting fixture mutations."""
    if MW.projectManager.session.is_dirty:
        MW.projectManager.session.mark_clean()
    assert MW.projectManager.closeProject()


@pytest.fixture(scope="session")
def test_application():
    """Own the GUI only for tests that request a workspace fixture."""
    from manuskript.tests import prepare_test_application

    application = prepare_test_application()
    yield application
    _app, window = application
    closeProjectDiscardingChanges(window)
    # QApplication is process-global, but its MainWindow must not be left for
    # Python and Qt DLL finalizers to dismantle in an arbitrary order. This is
    # particularly visible on Windows after tests open floating entity docks:
    # every assertion passes and the interpreter then exits with 0xC0000005.
    # Finish the native ownership graph while the event dispatcher is alive.
    from PyQt5.QtCore import QCoreApplication, QEvent

    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _app.processEvents()


@pytest.fixture(scope="session")
def MW(test_application):
    """
    Returns the mainWindow
    """
    _app, window = test_application
    return window

@pytest.fixture
def MWNoProject(MW):
    """
    Take the MainWindow and close andy possibly open project.
    """
    closeProjectDiscardingChanges(MW)
    assert MW.currentProject == None
    return MW

#: The empty project the suite is currently reusing.
_empty_project = {"path": None}


def _reusableEmptyProject(MW):
    """Whether the last test left this fixture's project untouched.

    Creating a project is the most expensive thing this suite does -- models
    built, widgets rebuilt, files written -- and it happens for every one of
    the several hundred tests that take this fixture. Most of them only read.

    The project's own dirty flag decides, because it already answers exactly
    this question: anything that changed a model marked it. A clean project
    is one that nothing has altered, so the next test may have it as it is.
    """
    project_path = _empty_project["path"]
    if project_path is None:
        return False
    manager = MW.projectManager
    if not manager.session.is_open or manager.session.is_dirty:
        return False
    return MW.currentProject == os.path.normpath(project_path)


@pytest.fixture(scope="session")
def empty_project_path(tmp_path_factory):
    """A reusable project path that is never held open by Python."""
    return tmp_path_factory.mktemp("empty-project") / "empty.msk"


@pytest.fixture
def MWEmptyProject(MW, empty_project_path):
    """
    Creates a MainWindow and load an empty project.

    Reused between tests that left it clean; rebuilt otherwise.
    """
    if _reusableEmptyProject(MW):
        return MW

    project_path = str(empty_project_path)
    _empty_project["path"] = project_path

    closeProjectDiscardingChanges(MW)
    assert MW.currentProject == None
    MW.welcome.createFile(project_path, overwrite=True)
    assert MW.currentProject != None
    return MW

    # If using with: @pytest.fixture(scope='session', autouse=True)
    # yield MW
    # # Properly destructed after. Otherwise: seg fault.
    # MW.deleteLater()

@pytest.fixture
def MWSampleProject(MW, tmp_path):
    """
    Creates a MainWindow and load a copy of the Acts sample project.
    """

    from manuskript import functions as F
    import os
    # Get the path of the first sample project. We assume it is here.
    spDir = F.appPath("sample-projects")
    lst = os.listdir(spDir)
    # We assume it's saved in folder, so there is a `name.msk` file and a
    # `name` folder.
    src = [f for f in lst if f[-4:] == ".msk" and f[:-4] in lst][0]
    src = os.path.join(spDir, src)
    # Copy to a path that is not held open. Windows denies replacement of
    # an open NamedTemporaryFile.
    project_file = tmp_path / "sample.msk"
    import shutil
    shutil.copyfile(src, project_file)
    shutil.copytree(src[:-4], project_file.with_suffix(""))
    closeProjectDiscardingChanges(MW)
    MW.projectManager.loadProject(str(project_file))
    assert MW.currentProject != None

    return MW
