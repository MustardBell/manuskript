import importlib
from unittest.mock import MagicMock, patch

from manuskript.domain.project import CloseDecision
from manuskript.ui.project_lifecycle import ProjectLifecycleView

project_lifecycle_module = importlib.import_module(
    "manuskript.ui.project_lifecycle"
)


def test_lifecycle_view_synchronizes_project_actions():
    window = MagicMock()
    view = ProjectLifecycleView(window)

    view.sync_to_state(project_open=True)

    window.actOpen.setEnabled.assert_called_once_with(False)
    window.menuRecents.setEnabled.assert_called_once_with(False)
    window.actSave.setEnabled.assert_called_once_with(True)
    window.actCloseProject.setEnabled.assert_called_once_with(True)


def test_lifecycle_view_maps_qt_dialog_result_to_domain_decision():
    window = MagicMock()
    view = ProjectLifecycleView(window)

    with patch.object(
        project_lifecycle_module,
        "QMessageBox",
    ) as message_box:
        message_box.Question = 0
        message_box.Save = 1
        message_box.Discard = 2
        message_box.Cancel = 4
        message_box.return_value.exec.return_value = message_box.Save

        decision = view.confirm_unsaved_changes()

    assert decision is CloseDecision.SAVE


def test_lifecycle_view_presents_failed_save_files():
    window = MagicMock()
    view = ProjectLifecycleView(window)
    failures = ("outline/scene.md", "world.opml")

    with patch.object(
        project_lifecycle_module,
        "ListDialog",
    ) as dialog_type, patch.object(
        project_lifecycle_module,
        "QListWidgetItem",
    ) as list_item:
        view.show_save_failures(failures)

    dialog = dialog_type.return_value
    dialog_type.assert_called_once_with(window)
    dialog.open.assert_called_once_with()
    assert [call.args[0] for call in list_item.call_args_list] == list(
        failures
    )
