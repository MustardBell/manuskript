from unittest.mock import MagicMock

from PyQt5.QtWidgets import QWidget

from manuskript.ui.workspace_transfers import (
    WorkspaceTransferController,
    WorkspaceTransferViews,
)


def transfer_fixture(qt_version="5.15.3", proceed=True):
    parent = QWidget()
    centered = []
    created = {"import": [], "export": []}
    confirmation = MagicMock(return_value=proceed)
    context = object()

    def create(name):
        dialog = QWidget(parent)
        created[name].append(dialog)
        return dialog

    views = WorkspaceTransferViews(
        center=centered.append,
        translate=lambda text: text,
        create_import=lambda: create("import"),
        create_export=lambda: create("export"),
        export_context=lambda: context,
        confirm_unsafe_import=confirmation,
        qt_version=lambda: qt_version,
        pyqt_version=lambda: "5.15.6",
    )
    return (
        WorkspaceTransferController(views),
        centered,
        created,
        confirmation,
        context,
    )


def test_import_and_export_have_independent_dialog_lifecycles():
    controller, centered, created, _confirm, _context = (
        transfer_fixture()
    )

    imported = controller.show_import()
    exported = controller.show_export()

    assert imported is controller.import_dialog
    assert exported is controller.export_dialog
    assert imported is not exported
    assert not imported.isHidden()
    assert not exported.isHidden()
    assert centered == [imported, exported]

    replacement = controller.show_export()

    assert imported is controller.import_dialog
    assert exported.isHidden()
    assert replacement is controller.export_dialog
    assert len(created["import"]) == 1
    assert len(created["export"]) == 2
    assert not hasattr(controller, "window")
    assert not hasattr(controller, "mw")
    controller.close_all()


def test_unsafe_import_can_be_cancelled_before_dialog_creation():
    controller, centered, created, confirmation, _context = (
        transfer_fixture(qt_version="5.12.9", proceed=False)
    )

    assert controller.show_import() is None

    confirmation.assert_called_once()
    assert created["import"] == []
    assert centered == []


def test_export_context_is_delegated_to_the_live_provider():
    controller, _centered, _created, _confirm, context = (
        transfer_fixture()
    )

    assert controller.export_context() is context


def test_main_window_owns_import_and_export_without_transfer_methods(
        MWSampleProject):
    window = MWSampleProject

    imported = window.workspaceTransfers.show_import()
    exported = window.workspaceTransfers.show_export()
    try:
        assert imported is window.workspaceTransfers.import_dialog
        assert exported is window.workspaceTransfers.export_dialog
        assert imported.parentWidget() is window
        assert exported.parentWidget() is window
        assert not hasattr(window, "dialog")
        assert not hasattr(window, "doImport")
        assert not hasattr(window, "doCompile")
        assert not hasattr(window, "exportContext")
        assert not hasattr(window, "conversionAugmentations")
    finally:
        window.workspaceTransfers.close_all()
