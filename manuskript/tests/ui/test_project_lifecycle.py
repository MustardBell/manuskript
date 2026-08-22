import importlib
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

from manuskript.domain.project import CloseDecision
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.project_lifecycle_views import ProjectLifecycleViews
from manuskript.ui.views.textEditView import textEditView

project_lifecycle_module = importlib.import_module(
    "manuskript.ui.project_lifecycle"
)


def lifecycle_for(window):
    return ProjectLifecycleView(
        window.projectRuntime,
        ProjectLifecycleViews.for_window(window),
    )


def test_lifecycle_view_synchronizes_project_actions():
    window = MagicMock()
    view = lifecycle_for(window)

    view.sync_to_state(project_open=True)

    window.actOpen.setEnabled.assert_called_once_with(False)
    window.menuRecents.setEnabled.assert_called_once_with(False)
    window.actSave.setEnabled.assert_called_once_with(True)
    window.actCloseProject.setEnabled.assert_called_once_with(True)


def test_lifecycle_view_has_no_main_window_service_locator():
    window = MagicMock()
    view = lifecycle_for(window)

    assert not hasattr(view, "window")
    assert view.runtime is window.projectRuntime


def test_lifecycle_view_maps_qt_dialog_result_to_domain_decision():
    window = MagicMock()
    window.projectRuntime.currentProject = "/books/example.msk"
    view = lifecycle_for(window)

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
    assert message_box.call_args.args[-1] is window


def test_lifecycle_view_presents_failed_save_files():
    window = MagicMock()
    view = lifecycle_for(window)
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
    open_indexes = [1, ["scene-1"], None]
    editor = window.corePanels.editor.editor
    window.surfaceHost.instance.return_value.widget.editor = editor
    editor.tabSplitter.openIndexes.return_value = open_indexes
    original_last_tab = window.projectRuntime.settingsManager.lastTab
    view = lifecycle_for(window)

    view.capture_project_state()
    view.prepare_close()

    # Open documents remain project-compatible state. The active surface is
    # window state now, so the obsolete tab number is preserved rather than
    # rewritten into formats 0 and 1.
    settings = window.projectRuntime.settingsManager
    assert settings.lastTab is original_last_tab
    assert settings.openIndexes == open_indexes
    editor.close.assert_called_once_with()
    editor.closeAllTabs.assert_called_once_with()
    window.pluginUi.prepare_project_close.assert_called_once_with()


def test_lifecycle_view_flushes_every_model_backed_text_editor():
    window = MagicMock()
    first = MagicMock()
    second = MagicMock()
    window.findChildren.return_value = [first, second]
    view = lifecycle_for(window)

    view.flush_pending_edits()

    window.findChildren.assert_called_once_with(textEditView)
    first.submit.assert_called_once_with()
    second.submit.assert_called_once_with()
    # Not the project's shared buffers: those are one per document however
    # many windows show it, and the project flushes them itself. A window
    # doing it too would repeat the whole flush per window.
    window.projectRuntime.documentBuffers.flush.assert_not_called()


def test_close_then_open_rebinds_outline_models_without_stale_delegates():
    """Native Qt model replacement is isolated and hard-limited.

    A stale delegate is capable of terminating the interpreter instead of
    raising.  Keeping this in a child process makes that failure diagnosable
    and prevents one lifecycle regression from taking the whole suite down.
    """
    script = r'''
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import QStyleOptionViewItem, qApp

from manuskript.enums import Outline
from manuskript.models import outlineItem
from manuskript.tests import prepare_test_application

_application, window = prepare_test_application()
with tempfile.TemporaryDirectory() as directory:
    first_project = Path(directory) / "first.msk"
    window.welcome.createFile(str(first_project), overwrite=True)
    item = outlineItem(title="Scene", _type="md")
    window.projectRuntime.models.outline.appendItem(item)
    old_model = window.projectRuntime.models.outline
    old_index = old_model.indexFromItem(item)
    pov_index = old_index.sibling(old_index.row(), Outline.POV)
    outline = window.corePanels.outline.treeOutlineOutline
    old_delegate = outline.itemDelegateForColumn(Outline.POV)
    window.projectManager.session.mark_clean()

    assert window.projectManager.closeProject()
    qApp.processEvents()
    assert outline.model() is None
    assert window.corePanels.project_tree.tree.model() is None
    assert old_delegate.mdlCharacter is None
    old_delegate.sizeHint(QStyleOptionViewItem(), pov_index)

    next_project = Path(directory) / "mayor.msk"
    window.welcome.createFile(str(next_project), overwrite=True)
    qApp.processEvents()
    assert window.currentProject == str(next_project)
    assert outline.model() is window.projectRuntime.models.outline
    assert window.corePanels.project_tree.tree.model() is window.projectRuntime.models.outline
    assert outline.itemDelegateForColumn(
        Outline.POV
    ).mdlCharacter is window.projectRuntime.models.characters
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
