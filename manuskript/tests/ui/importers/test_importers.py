#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Tests for settingsWindow"""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QModelIndex

from manuskript.ui.importers.import_context import ImportContextProvider


def test_import_context_provider_resolves_live_project_models():
    state = {
        "models": SimpleNamespace(
            outline=object(),
            characters=object(),
            labels=object(),
            statuses=object(),
        )
    }
    provider = ImportContextProvider(
        models=lambda: state["models"],
        settings=object(),
        current_outline_index=lambda: QModelIndex(),
        show_status=lambda *_args: None,
    )

    first = provider.create()
    next_models = SimpleNamespace(
        outline=object(),
        characters=object(),
        labels=object(),
        statuses=object(),
    )
    state["models"] = next_models
    second = provider.create()

    assert first.outline_model is not second.outline_model
    assert second.outline_model is next_models.outline
    assert second.character_model is next_models.characters


def test_loadImportWiget(MWSampleProject):
    """
    Simply tests that import widget loads properly.
    """
    MW = MWSampleProject
    selected = MW.projectRuntime.models.outline.index(0, 0, QModelIndex())
    MW.corePanels.project_tree.tree.setCurrentIndex(selected)

    # Loading from mainWindow
    MW.workspaceTransfers.show_import()
    I = MW.workspaceTransfers.import_dialog
    assert I.isVisible()
    assert I.context.outline_model is MW.projectRuntime.models.outline
    assert I.context.character_model is MW.projectRuntime.models.characters
    assert I.context.label_model is MW.projectRuntime.models.labels
    assert I.context.status_model is MW.projectRuntime.models.statuses

    settings = I.settingsWidget
    proxy = settings.treeGeneralParent.model()
    assert proxy.mapToSource(settings.getParentIndex()) == selected
    settings.chkGeneralParent.setChecked(True)
    assert settings.importUnderID() == MW.projectRuntime.models.outline.ID(selected)

    status = MagicMock()
    I.context = replace(I.context, show_status=status)
    with patch.object(I, "startImport") as start_import:
        I.doImport()

    start_import.assert_called_once_with(MW.projectRuntime.models.outline)
    status.assert_called_once_with("Import complete!", 5000)
    assert not I.isVisible()


def test_import_batches_aggregate_word_count_updates(
        MWSampleProject):
    model = MWSampleProject.projectRuntime.models.outline
    MWSampleProject.workspaceTransfers.show_import()
    dialog = MWSampleProject.workspaceTransfers.import_dialog
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
