import unittest
from unittest.mock import MagicMock, patch

from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.domain.project import CloseDecision, ProjectState
from manuskript.projectManager import ProjectManager
from manuskript.settingsManager import SettingsManager
from manuskript.ui.project_lifecycle import ProjectLifecycleView


class TestProjectManager(unittest.TestCase):

    def setUp(self):
        self.window = MagicMock()
        settings_manager = SettingsManager()
        with patch.object(settings_manager, "apply_loaded_settings_effects"):
            settings_manager.reset_to_defaults()
        self.window.settingsManager = settings_manager
        self.storage = MagicMock()
        self.status_reporter = MagicMock()
        self.autosave = MagicMock()
        self.last_project_store = MagicMock()
        self.lifecycle_view = ProjectLifecycleView(self.window)
        self.lifecycle_view.show_save_failures = MagicMock()
        self.lifecycle_view.show_load_failures = MagicMock()
        self.project_manager = ProjectManager(
            self.lifecycle_view,
            storage=self.storage,
            status_reporter=self.status_reporter,
            autosave=self.autosave,
            last_project_store=self.last_project_store,
        )

    @patch('os.path.exists')
    def test_load_project_file_not_exists(self, mock_exists):
        # Test case: file doesn't exist
        mock_exists.return_value = False
        expected_message = "The file {} does not exist. Has it been moved or deleted?"
        self.window.tr.return_value = expected_message
        
        result = self.project_manager.loadProject("non_existent_project.msk")
        
        self.assertFalse(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLOSED)
        # Verify the translation function was called with correct message
        self.window.tr.assert_called_with("The file {} does not exist. Has it been moved or deleted?")
        # Verify the status reporter received the translated critical message.
        self.status_reporter.assert_called_once_with(
            expected_message.format("non_existent_project.msk"),
            importance=3,
        )
        
    @patch('os.path.exists')
    def test_load_project_file_exists(self, mock_exists):
        # Test case: file exists - should proceed with loading
        mock_exists.return_value = True
        
        # Mock the loading methods to avoid complex setup
        with patch.object(self.project_manager, 'loadEmptyDatas'), \
             patch.object(self.project_manager, 'loadDatas', return_value=True), \
             patch.object(self.window, 'makeConnections'):
            
            result = self.project_manager.loadProject("existing_project.msk")
            
            self.assertTrue(result)
            self.assertEqual(
                self.project_manager.session.state, ProjectState.CLEAN
            )
            self.assertEqual(
                self.project_manager.currentProject, "existing_project.msk"
            )
            # Should not call the error message about file not existing
            error_calls = [call for call in self.window.tr.call_args_list 
                          if "does not exist" in str(call)]
            self.assertEqual(len(error_calls), 0, "Should not show file not found error")
            
            # Should not report a critical status message.
            error_status_calls = [call for call in self.status_reporter.call_args_list
                                if len(call.kwargs) > 0 and call.kwargs.get('importance') == 3]
            self.assertEqual(len(error_status_calls), 0, "Should not show error status message")

    def test_project_change_transitions_session_to_dirty(self):
        self.project_manager.session.open("project.msk")
        self.window.settingsManager.autoSaveNoChanges = False

        result = self.project_manager.startTimerNoChanges()

        self.assertTrue(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.DIRTY)
        self.autosave.schedule_after_change.assert_called_once_with()

    def test_successful_save_transitions_session_to_clean(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = ProjectSaveResult()

        with patch.object(
            self.lifecycle_view,
            "capture_project_state",
        ) as capture_project_state:
            result = self.project_manager.saveDatas()

        self.assertTrue(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLEAN)
        capture_project_state.assert_called_once_with()
        self.storage.save.assert_called_once()
        context = self.storage.save.call_args.args[0]
        self.assertEqual(context.project_file, "project.msk")
        self.assertIs(context.models, self.project_manager.models)
        self.assertIs(context.settings, self.window.settingsManager)

    def test_failed_save_preserves_dirty_state(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = ProjectSaveResult(
            failed_files=("outline/scene.md",)
        )

        result = self.project_manager.saveDatas()

        self.assertFalse(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.DIRTY)

    def test_failed_automatic_save_prevents_project_close(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.window.settingsManager.saveOnQuit = True

        with patch.object(self.project_manager, "saveDatas", return_value=False):
            result = self.project_manager.closeProject()

        self.assertFalse(result)
        self.assertTrue(self.project_manager.session.is_open)

    def test_save_on_quit_persists_even_when_content_is_clean(self):
        self.project_manager.session.open("project.msk")
        self.window.settingsManager.saveOnQuit = True

        with patch.object(
            self.project_manager,
            "saveDatas",
            return_value=True,
        ) as save, patch.object(
            self.project_manager,
            "loadEmptyDatas",
        ):
            result = self.project_manager.closeProject()

        self.assertTrue(result)
        save.assert_called_once_with()
        self.assertFalse(self.project_manager.session.is_open)

    def test_cancelled_unsaved_changes_prevent_project_close(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.window.settingsManager.saveOnQuit = False

        with patch.object(
            self.project_manager, "handleUnsavedChanges", return_value=False
        ):
            result = self.project_manager.closeProject()

        self.assertFalse(result)
        self.assertTrue(self.project_manager.session.is_open)
        self.assertTrue(self.project_manager.session.is_dirty)

    def test_unsaved_change_decision_is_supplied_by_lifecycle_view(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        with patch.object(
            self.lifecycle_view,
            "confirm_unsaved_changes",
            return_value=CloseDecision.CANCEL,
        ):
            self.assertFalse(
                self.project_manager.handleUnsavedChanges()
            )

        with patch.object(
            self.lifecycle_view,
            "confirm_unsaved_changes",
            return_value=CloseDecision.DISCARD,
        ):
            self.assertTrue(
                self.project_manager.handleUnsavedChanges()
            )

    def test_change_signal_after_close_is_ignored(self):
        result = self.project_manager.startTimerNoChanges()

        self.assertFalse(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLOSED)

    def test_failed_save_as_restores_original_project_path(self):
        self.project_manager.session.open("original.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = ProjectSaveResult(
            failed_files=("renamed.msk",)
        )

        result = self.project_manager.saveDatas("renamed.msk")

        self.assertFalse(result)
        self.assertEqual(self.project_manager.currentProject, "original.msk")
        self.assertTrue(self.project_manager.projectDirty)

    def test_loading_second_project_is_rejected(self):
        self.project_manager.session.open("first.msk")

        result = self.project_manager.loadProject(
            "second.msk", loadFromFile=False
        )

        self.assertFalse(result)
        self.assertEqual(self.project_manager.currentProject, "first.msk")

    def test_empty_project_models_are_requested_from_factory(self):
        factory = MagicMock()
        models = MagicMock()
        factory.create.return_value = models
        self.project_manager.model_factory = factory

        result = self.project_manager.loadEmptyDatas()

        self.assertIs(result, models)
        self.assertIs(self.project_manager.models, models)
        factory.create.assert_called_once_with(
            self.window,
            self.window.settingsManager,
        )
        models.install_on.assert_called_once_with(self.window)

    def test_save_permission_failures_are_presented_by_lifecycle_view(self):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        failures = ("outline/scene.md", "world.opml")
        self.storage.save.return_value = ProjectSaveResult(
            failed_files=failures
        )

        with patch.object(
            self.lifecycle_view, "show_save_failures"
        ) as show_failures:
            result = self.project_manager.saveDatas()

        self.assertFalse(result)
        show_failures.assert_called_once_with(failures)

    def test_revision_restore_replaces_models_through_project_owner(self):
        self.project_manager.session.open("project.msk")
        self.window.tabMain.currentIndex.return_value = 0
        self.window.mainEditor.tabSplitter.openIndexes.return_value = []
        previous_models = MagicMock()
        replacement_models = MagicMock()
        self.project_manager.models = previous_models
        self.storage.save.side_effect = [
            ProjectSaveResult(),
            ProjectSaveResult(),
        ]
        snapshot = MagicMock()
        snapshot.commit_id = "a" * 40
        snapshot.models = replacement_models
        snapshot.load_result = ProjectLoadResult()
        snapshot.settings.save.return_value = (
            self.window.settingsManager.save()
        )

        with patch.object(
            self.lifecycle_view,
            "flush_pending_edits",
        ) as flush, patch.object(
            self.lifecycle_view,
            "prepare_model_replacement",
        ) as prepare:
            result = self.project_manager.restoreRevisionSnapshot(
                snapshot
            )

        self.assertTrue(result)
        self.assertIs(
            self.project_manager.models,
            replacement_models,
        )
        flush.assert_called_once_with()
        prepare.assert_called_once_with()
        self.assertEqual(self.storage.save.call_count, 2)
        self.assertEqual(
            self.project_manager.session.state,
            ProjectState.CLEAN,
        )
        self.storage.load.assert_not_called()

    def test_failed_revision_save_reinstalls_and_rewrites_previous_state(
        self,
    ):
        self.project_manager.session.open("project.msk")
        self.window.tabMain.currentIndex.return_value = 0
        self.window.mainEditor.tabSplitter.openIndexes.return_value = []
        previous_models = MagicMock()
        replacement_models = MagicMock()
        self.project_manager.models = previous_models
        self.storage.save.side_effect = [
            ProjectSaveResult(),
            ProjectSaveResult(failed_files=("outline/scene.md",)),
            ProjectSaveResult(),
        ]
        snapshot = MagicMock()
        snapshot.commit_id = "b" * 40
        snapshot.models = replacement_models
        snapshot.load_result = ProjectLoadResult()
        snapshot.settings.save.return_value = (
            self.window.settingsManager.save()
        )

        result = self.project_manager.restoreRevisionSnapshot(snapshot)

        self.assertFalse(result)
        self.assertIs(self.project_manager.models, previous_models)
        self.assertEqual(self.storage.save.call_count, 3)
        self.assertEqual(
            self.project_manager.session.state,
            ProjectState.CLEAN,
        )

    def test_invalid_revision_snapshot_never_touches_live_project(self):
        self.project_manager.session.open("project.msk")
        previous_models = MagicMock()
        self.project_manager.models = previous_models
        snapshot = MagicMock()
        snapshot.commit_id = "c" * 40
        snapshot.load_result = ProjectLoadResult(
            fatal_errors=("Malformed snapshot",)
        )

        result = self.project_manager.restoreRevisionSnapshot(snapshot)

        self.assertFalse(result)
        self.assertIs(self.project_manager.models, previous_models)
        self.storage.save.assert_not_called()

    def test_load_permission_failures_are_presented_by_lifecycle_view(self):
        failures = ("outline/scene.md",)
        self.storage.load.return_value = ProjectLoadResult(
            unreadable_files=failures
        )

        with patch.object(
            self.lifecycle_view, "show_load_failures"
        ) as show_failures:
            result = self.project_manager.loadDatas("project.msk")

        self.assertTrue(result)
        show_failures.assert_called_once_with(failures)

    def test_fatal_load_failure_is_reported_without_success_feedback(self):
        self.storage.load.return_value = ProjectLoadResult(
            fatal_errors=("Malformed plots.xml",)
        )

        result = self.project_manager.loadDatas("project.msk")

        self.assertFalse(result)
        self.status_reporter.assert_called_once()
        assert self.status_reporter.call_args.args[1] == 5000
        assert self.status_reporter.call_args.kwargs == {
            "importance": 3
        }

if __name__ == '__main__':
    unittest.main()
