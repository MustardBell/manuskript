#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Tests for settingsWindow"""

from dataclasses import replace
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QModelIndex


def test_loadImportWiget(MWSampleProject):
    """
    Simply tests that import widget loads properly.
    """
    MW = MWSampleProject
    selected = MW.mdlOutline.index(0, 0, QModelIndex())
    MW.treeRedacOutline.setCurrentIndex(selected)

    # Loading from mainWindow
    MW.doImport()
    I = MW.dialog
    assert I.isVisible()
    assert I.context.outline_model is MW.mdlOutline
    assert I.context.character_model is MW.mdlCharacter
    assert I.context.label_model is MW.mdlLabels
    assert I.context.status_model is MW.mdlStatus

    settings = I.settingsWidget
    proxy = settings.treeGeneralParent.model()
    assert proxy.mapToSource(settings.getParentIndex()) == selected
    settings.chkGeneralParent.setChecked(True)
    assert settings.importUnderID() == MW.mdlOutline.ID(selected)

    status = MagicMock()
    I.context = replace(I.context, show_status=status)
    with patch.object(I, "startImport") as start_import:
        I.doImport()

    start_import.assert_called_once_with(MW.mdlOutline)
    status.assert_called_once_with("Import complete!", 5000)
    assert not I.isVisible()
