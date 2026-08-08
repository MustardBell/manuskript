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


@pytest.fixture(scope="session", autouse=True)
def closeProjectAfterTests():
    """Leave Qt with a closed project so teardown cannot show a save dialog."""
    yield
    from manuskript.tests import MW as window
    closeProjectDiscardingChanges(window)


@pytest.fixture
def MW():
    """
    Returns the mainWindow
    """
    from manuskript.tests import MW as window
    return window

@pytest.fixture
def MWNoProject(MW):
    """
    Take the MainWindow and close andy possibly open project.
    """
    closeProjectDiscardingChanges(MW)
    assert MW.currentProject == None
    return MW

#: The empty project the suite is currently reusing, and its temporary file.
#: Held at module scope so the file is not collected out from under it.
_empty_project = {"file": None}


def _reusableEmptyProject(MW):
    """Whether the last test left this fixture's project untouched.

    Creating a project is the most expensive thing this suite does -- models
    built, widgets rebuilt, files written -- and it happens for every one of
    the several hundred tests that take this fixture. Most of them only read.

    The project's own dirty flag decides, because it already answers exactly
    this question: anything that changed a model marked it. A clean project
    is one that nothing has altered, so the next test may have it as it is.
    """
    holder = _empty_project["file"]
    if holder is None:
        return False
    manager = MW.projectManager
    if not manager.session.is_open or manager.session.is_dirty:
        return False
    return MW.currentProject == os.path.normpath(holder.name)


@pytest.fixture
def MWEmptyProject(MW):
    """
    Creates a MainWindow and load an empty project.

    Reused between tests that left it clean; rebuilt otherwise.
    """
    if _reusableEmptyProject(MW):
        return MW

    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".msk")
    _empty_project["file"] = tf

    closeProjectDiscardingChanges(MW)
    assert MW.currentProject == None
    MW.welcome.createFile(tf.name, overwrite=True)
    assert MW.currentProject != None
    return MW

    # If using with: @pytest.fixture(scope='session', autouse=True)
    # yield MW
    # # Properly destructed after. Otherwise: seg fault.
    # MW.deleteLater()

@pytest.fixture
def MWSampleProject(MW):
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
    # Copy to a temp file
    import tempfile
    tf = tempfile.NamedTemporaryFile(suffix=".msk")
    import shutil
    shutil.copyfile(src, tf.name)
    shutil.copytree(src[:-4], tf.name[:-4])
    closeProjectDiscardingChanges(MW)
    MW.projectManager.loadProject(tf.name)
    assert MW.currentProject != None

    return MW
