import unittest
from unittest.mock import MagicMock, patch

from manuskript.domain.persistence import ProjectSaveResult
from manuskript.projectManager import ProjectManager
from manuskript.ui.project_lifecycle import ProjectLifecycleView


class TestProjectManagerAutosave(unittest.TestCase):

    def setUp(self):
        self.window = MagicMock()
        self.window.tr = lambda text: text
        self.storage = MagicMock()
        self.storage.save.return_value = ProjectSaveResult()
        self.autosave = MagicMock()
        self.last_project_store = MagicMock()
        self.project_manager = ProjectManager(
            ProjectLifecycleView(self.window),
            storage=self.storage,
            autosave=self.autosave,
            last_project_store=self.last_project_store,
        )

    def _load_project(self, auto_save=True, after_change=True):
        settings = self.window.settingsManager
        settings.autoSave = auto_save
        settings.autoSaveDelay = 15
        settings.autoSaveNoChanges = after_change
        settings.autoSaveNoChangesDelay = 3
        settings.openIndexes = []
        settings.viewSettings = {"Tree": {"iconSize": 24}}
        settings.lastTab = 0
        settings.corkSizeFactor = 100
        settings.spellcheck = False
        settings.folderView = False
        settings.viewMode = "fiction"

        with patch("os.path.exists", return_value=True), patch.object(
            self.project_manager, "loadDatas", return_value=True
        ), patch.object(
            self.project_manager, "loadEmptyDatas"
        ), patch.object(
            self.window.settingsManager, "reset_to_defaults"
        ):
            return self.project_manager.loadProject(
                "dummy_project.msk"
            )

    def test_load_configures_autosave_policy(self):
        self.assertTrue(self._load_project())

        self.autosave.configure.assert_called_once_with(
            periodic_enabled=True,
            periodic_delay_minutes=15,
            after_change_enabled=True,
            after_change_delay_seconds=3,
        )

    def test_project_change_delegates_idle_save_scheduling(self):
        self._load_project()
        self.project_manager.startTimerNoChanges()

        self.autosave.schedule_after_change.assert_called_once_with()
        self.assertTrue(self.project_manager.projectDirty)

    def test_save_stops_pending_idle_schedule(self):
        self._load_project()

        self.project_manager.saveDatas()

        self.autosave.saving_started.assert_called_once_with()

    def test_close_stops_all_autosave_schedules(self):
        self._load_project()

        with patch.object(
            self.project_manager,
            "handleUnsavedChanges",
            return_value=True,
        ), patch.object(
            self.project_manager,
            "loadEmptyDatas",
        ):
            self.project_manager.closeProject()

        self.autosave.stop.assert_called_once_with()

    def test_last_project_path_tracks_load_save_and_close(self):
        self._load_project()
        self.last_project_store.remember_last_project.assert_called_once_with(
            "dummy_project.msk"
        )

        self.project_manager.session.mark_dirty()
        self.project_manager.saveDatas("renamed.msk")
        self.last_project_store.remember_last_project.assert_called_with(
            "renamed.msk"
        )

        with patch.object(
            self.project_manager,
            "loadEmptyDatas",
        ):
            self.project_manager.closeProject()
        self.last_project_store.clear_last_project.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
