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


def test_import_batches_aggregate_word_count_updates(
        MWSampleProject):
    model = MWSampleProject.mdlOutline
    MWSampleProject.doImport()
    dialog = MWSampleProject.dialog
    dialog.fileName = "import.md"
    dialog.settingsWidget.importInTopLevelFolder = MagicMock(
        return_value=False
    )
    imported = MagicMock()
    imported.startImport.return_value = []
    dialog._format = imported

    with patch.object(
        model,
        "batchWordCountUpdates",
        wraps=model.batchWordCountUpdates,
    ) as batch:
        assert dialog.startImport(model)

    batch.assert_called_once_with()
    imported.startImport.assert_called_once()
    dialog.close()
