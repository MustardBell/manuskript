from types import SimpleNamespace
from unittest.mock import MagicMock

from manuskript.ui.project_upgrade_dialog import ProjectUpgradeDialog


def _dialog():
    manager = MagicMock()
    manager.currentProject = "/books/source.msk"
    manager.storage.canonical_project = SimpleNamespace(format_version=1)
    manager.saveDatas.return_value = True
    service = MagicMock()
    report = MagicMock()
    report.render_text.return_value = "Format 1 → Format 2\nOutline: 2 / 2 converted"
    service.upgrade_copy.return_value = report
    return ProjectUpgradeDialog(manager, service), manager, service


def test_upgrade_dialog_saves_then_creates_copy_and_shows_report():
    dialog, manager, service = _dialog()
    dialog.destinationEdit.setText("/books/upgraded.msk")

    assert dialog._upgrade()

    manager.saveDatas.assert_called_once_with()
    service.upgrade_copy.assert_called_once_with(
        "/books/source.msk", "/books/upgraded.msk"
    )
    assert "2 / 2" in dialog.reportEdit.toPlainText()
    assert dialog.openButton.isEnabled()
    assert dialog.destinationEdit.accessibleName() == "Upgrade destination"
    assert dialog.reportEdit.accessibleName() == "Migration report"
    dialog.close()


def test_upgrade_dialog_does_not_migrate_unsaved_or_unsupported_project():
    dialog, manager, service = _dialog()
    manager.saveDatas.return_value = False

    assert not dialog._upgrade()
    service.upgrade_copy.assert_not_called()
    assert "not saved" in dialog.messageLabel.text()
    dialog.close()

    unsupported, _manager, _service = _dialog()
    unsupported.projectManager.storage.canonical_project.format_version = 2
    unsupported._update_availability()
    assert not unsupported.upgradeButton.isEnabled()
    unsupported.close()


def test_upgrade_dialog_logs_and_displays_migration_failure(caplog):
    dialog, _manager, service = _dialog()
    service.upgrade_copy.side_effect = ValueError("reopen validation failed")

    with caplog.at_level("ERROR"):
        assert not dialog._upgrade()

    assert "reopen validation failed" in dialog.messageLabel.text()
    assert "reopen validation failed" in dialog.reportEdit.toPlainText()
    assert "Project Format upgrade failed" in caplog.text
    dialog.close()


def test_open_upgraded_copy_closes_source_before_opening_destination():
    dialog, manager, _service = _dialog()
    dialog._upgradedFile = "/books/upgraded.msk"
    manager.closeProject.return_value = True
    manager.loadProject.return_value = True

    assert dialog._open_upgraded()

    manager.closeProject.assert_called_once_with()
    manager.loadProject.assert_called_once_with("/books/upgraded.msk")


def test_failed_open_of_upgraded_copy_reopens_the_source():
    dialog, manager, _service = _dialog()
    dialog._upgradedFile = "/books/upgraded.msk"
    manager.closeProject.return_value = True
    manager.loadProject.side_effect = (False, True)

    assert not dialog._open_upgraded()

    assert manager.loadProject.call_args_list == [
        (("/books/upgraded.msk",), {}),
        (("/books/source.msk",), {}),
    ]
    assert "original project was reopened" in dialog.messageLabel.text()
