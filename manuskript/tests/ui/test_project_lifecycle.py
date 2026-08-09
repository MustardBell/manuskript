import importlib
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QStyleOptionViewItem, qApp

from manuskript.domain.project import CloseDecision
from manuskript.enums import Outline
from manuskript.models import outlineItem
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.views.textEditView import textEditView

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


def test_lifecycle_view_captures_project_state_before_cleanup():
    window = MagicMock()
    window.tabMain.currentIndex.return_value = 6
    open_indexes = [1, ["scene-1"], None]
    window.mainEditor.tabSplitter.openIndexes.return_value = open_indexes
    view = ProjectLifecycleView(window)

    view.capture_project_state()
    view.prepare_close()

    # Captured onto the runtime's settings: they belong to the project,
    # not to whichever window happened to be closing.
    settings = window.projectRuntime.settingsManager
    assert settings.lastTab == 6
    assert settings.openIndexes == open_indexes
    window.mainEditor.close.assert_called_once_with()
    window.mainEditor.closeAllTabs.assert_called_once_with()
    window.pluginUi.prepare_project_close.assert_called_once_with()


def test_lifecycle_view_flushes_every_model_backed_text_editor():
    window = MagicMock()
    first = MagicMock()
    second = MagicMock()
    window.findChildren.return_value = [first, second]
    view = ProjectLifecycleView(window)

    view.flush_pending_edits()

    window.findChildren.assert_called_once_with(textEditView)
    first.submit.assert_called_once_with()
    second.submit.assert_called_once_with()
    # Not the project's shared buffers: those are one per document however
    # many windows show it, and the project flushes them itself. A window
    # doing it too would repeat the whole flush per window.
    window.projectRuntime.documentBuffers.flush.assert_not_called()


def test_close_then_open_rebinds_outline_models_without_stale_delegates(
        MWEmptyProject, tmp_path):
    window = MWEmptyProject
    item = outlineItem(title="Scene", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    old_model = window.projectRuntime.models.outline
    old_index = old_model.indexFromItem(item)
    pov_index = old_index.sibling(old_index.row(), Outline.POV)
    old_delegate = window.treeOutlineOutline.itemDelegateForColumn(
        Outline.POV
    )
    window.projectManager.session.mark_clean()

    assert window.projectManager.closeProject()
    qApp.processEvents()

    assert window.treeOutlineOutline.model() is None
    assert window.corePanels.project_tree.tree.model() is None
    assert old_delegate.mdlCharacter is None
    old_delegate.sizeHint(QStyleOptionViewItem(), pov_index)

    next_project = tmp_path / "mayor.msk"
    window.welcome.createFile(str(next_project), overwrite=True)
    qApp.processEvents()

    assert window.currentProject == str(next_project)
    assert (
        window.treeOutlineOutline.model()
        is window.projectRuntime.models.outline
    )
    assert (
        window.corePanels.project_tree.tree.model()
        is window.projectRuntime.models.outline
    )
    assert (
        window.treeOutlineOutline.itemDelegateForColumn(
            Outline.POV
        ).mdlCharacter
        is window.projectRuntime.models.characters
    )
