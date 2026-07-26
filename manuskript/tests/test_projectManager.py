import unittest
from unittest.mock import MagicMock, patch

from manuskript.domain.project import ProjectState
from manuskript.projectManager import ProjectManager
from manuskript.settingsManager import SettingsManager


class TestProjectManager(unittest.TestCase):

    def setUp(self):
        self.window = MagicMock()
        settings_manager = SettingsManager()
        with patch.object(settings_manager, "apply_loaded_settings_effects"):
            settings_manager.reset_to_defaults()
        self.window.settingsManager = settings_manager
        self.storage = MagicMock()
        self.project_manager = ProjectManager(self.window, storage=self.storage)

    @patch('manuskript.functions.statusMessage')
    @patch('os.path.exists')
    def test_load_project_file_not_exists(self, mock_exists, mock_status_message):
        # Test case: file doesn't exist
        mock_exists.return_value = False
        expected_message = "The file {} does not exist. Has it been moved or deleted?"
        self.window.tr.return_value = expected_message
        
        result = self.project_manager.loadProject("non_existent_project.msk")
        
        self.assertFalse(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLOSED)
        # Verify the translation function was called with correct message
        self.window.tr.assert_called_with("The file {} does not exist. Has it been moved or deleted?")
        # Verify statusMessage was called with the translated message and importance=3
        mock_status_message.assert_called_once_with(expected_message.format("non_existent_project.msk"), importance=3)
        
    @patch('manuskript.functions.statusMessage')
    @patch('os.path.exists')
    def test_load_project_file_exists(self, mock_exists, mock_status_message):
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
            
            # Should not call statusMessage with importance=3 (error level)
            error_status_calls = [call for call in mock_status_message.call_args_list 
                                if len(call.kwargs) > 0 and call.kwargs.get('importance') == 3]
            self.assertEqual(len(error_status_calls), 0, "Should not show error status message")

    def test_project_change_transitions_session_to_dirty(self):
        self.project_manager.session.open("project.msk")
        self.window.settingsManager.autoSaveNoChanges = False

        result = self.project_manager.startTimerNoChanges()

        self.assertTrue(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.DIRTY)

    @patch("manuskript.projectManager.F.statusMessage")
    def test_successful_save_transitions_session_to_clean(
        self, mock_status_message
    ):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = True

        result = self.project_manager.saveDatas()

        self.assertTrue(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLEAN)
        self.storage.save.assert_called_once_with(self.window)

    @patch("manuskript.projectManager.F.statusMessage")
    def test_failed_save_preserves_dirty_state(self, mock_status_message):
        self.project_manager.session.open("project.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = False

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

    def test_change_signal_after_close_is_ignored(self):
        result = self.project_manager.startTimerNoChanges()

        self.assertFalse(result)
        self.assertEqual(self.project_manager.session.state, ProjectState.CLOSED)

    @patch("manuskript.projectManager.F.statusMessage")
    def test_failed_save_as_restores_original_project_path(
        self, mock_status_message
    ):
        self.project_manager.session.open("original.msk")
        self.project_manager.session.mark_dirty()
        self.storage.save.return_value = False

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

if __name__ == '__main__':
    unittest.main()
