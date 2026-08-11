import unittest
from unittest.mock import MagicMock, patch

from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.domain.project import CloseDecision, ProjectState
from manuskript.projectManager import ProjectManager
from manuskript.services.project_view_registry import ProjectViewRegistry
from manuskript.settingsManager import SettingsManager
from manuskript.ui.project_lifecycle import ProjectLifecycleView
from manuskript.ui.project_lifecycle_views import ProjectLifecycleViews


def lifecycle_for(window):
    return ProjectLifecycleView(
        window.projectRuntime,
        ProjectLifecycleViews.for_window(window),
    )


class TestProjectManager(unittest.TestCase):

    def setUp(self):
        self.window = MagicMock()
        settings_manager = SettingsManager()
        with patch.object(settings_manager, "apply_loaded_settings_effects"):
            settings_manager.reset_to_defaults()
        # The project's own things live on the runtime.
        self.window.projectRuntime.settingsManager = settings_manager
        self.storage = MagicMock()
        self.status_reporter = MagicMock()
        self.autosave = MagicMock()
        self.last_project_store = MagicMock()
        self.lifecycle_view = lifecycle_for(self.window)
        self.lifecycle_view.show_save_failures = MagicMock()
        self.lifecycle_view.show_load_failures = MagicMock()
        self.project_manager = ProjectManager(
            self.lifecycle_view,
            settings_manager,
            self.window.projectRuntime.modelParent,
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
             patch.object(self.project_manager, 'loadDatas', return_value=True):
            
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
        self.window.projectRuntime.settingsManager.autoSaveNoChanges = False

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
        self.assertIs(
            context.settings,
            self.window.projectRuntime.settingsManager,
        )

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
        self.window.projectRuntime.settingsManager.saveOnQuit = True

        with patch.object(self.project_manager, "saveDatas", return_value=False):
            result = self.project_manager.closeProject()

        self.assertFalse(result)
        self.assertTrue(self.project_manager.session.is_open)

    def test_save_on_quit_persists_even_when_content_is_clean(self):
        self.project_manager.session.open("project.msk")
        self.window.projectRuntime.settingsManager.saveOnQuit = True

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
        self.window.projectRuntime.settingsManager.saveOnQuit = False

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
        # Parented to the runtime, not the window: Qt deletes children
        # with their parent, and a window closing is not the project
        # ending.
        factory.create.assert_called_once_with(
            self.window.projectRuntime.modelParent,
            self.window.projectRuntime.settingsManager,
        )
        # Returning the graph is the whole operation. Views discover it
        # through the shared runtime; the manager does not install aliases
        # on whichever window happened to trigger creation.

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
            self.window.projectRuntime.settingsManager.save()
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
        # Once per save, from inside the save, rather than once here: the
        # restore takes a snapshot of the project first and that snapshot
        # has to include what was just typed.
        self.assertEqual(flush.call_count, 2)
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
            self.window.projectRuntime.settingsManager.save()
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


class TestSaveFlushesPendingText(unittest.TestCase):
    """A save writes the models, so the models have to be current first.

    An explicit flush existed before a Git commit and before restoring a
    revision, but not before an ordinary save, an autosave, or the save a
    project close performs -- and a text editor holds what was typed for
    half a second before submitting it. Closing a secondary window does not
    run the project close at all, so its unsubmitted text had nothing left
    to write it out.
    """

    def setUp(self):
        self.window = MagicMock()
        settings_manager = SettingsManager()
        with patch.object(settings_manager, "apply_loaded_settings_effects"):
            settings_manager.reset_to_defaults()
        self.window.projectRuntime.settingsManager = settings_manager
        self.storage = MagicMock()
        self.view = lifecycle_for(self.window)
        self.view.flush_pending_edits = MagicMock()
        self.view.capture_project_state = MagicMock()
        self.view.show_save_failures = MagicMock()
        self.manager = ProjectManager(
            self.view,
            settings_manager,
            self.window.projectRuntime.modelParent,
            storage=self.storage,
            autosave=MagicMock(),
            last_project_store=MagicMock(),
        )

    def test_an_ordinary_save_flushes_first(self):
        self.manager.session.open("project.msk")
        self.storage.save.return_value = ProjectSaveResult()

        self.assertTrue(self.manager.saveDatas())

        self.view.flush_pending_edits.assert_called_once_with()

    def test_the_flush_happens_before_anything_is_written(self):
        """Flushing after the write would be no use at all."""
        self.manager.session.open("project.msk")
        self.storage.save.return_value = ProjectSaveResult()
        order = []
        self.view.flush_pending_edits.side_effect = (
            lambda: order.append("flush")
        )
        self.storage.save.side_effect = (
            lambda _context: order.append("save") or ProjectSaveResult()
        )

        self.manager.saveDatas()

        self.assertEqual(order, ["flush", "save"])

    def test_a_save_as_flushes_too(self):
        self.manager.session.open("project.msk")
        self.storage.save.return_value = ProjectSaveResult()

        self.manager.saveDatas("renamed.msk")

        self.view.flush_pending_edits.assert_called_once_with()

    def test_close_flushes_before_deciding_whether_project_is_dirty(self):
        """A delayed private edit must participate in the close decision."""
        self.manager.session.open("project.msk")
        self.manager.settings.saveOnQuit = False
        self.view.flush_pending_edits.side_effect = (
            self.manager.session.mark_dirty
        )
        with patch.object(
            self.view,
            "confirm_unsaved_changes",
            return_value=CloseDecision.CANCEL,
        ) as confirm:
            self.assertFalse(self.manager.settleBeforeClosing())

        self.view.flush_pending_edits.assert_called_once_with()
        confirm.assert_called_once_with()


#: Everything a lifecycle view is asked to do, and nothing else. The list
#: is the contract: a view shows a project and answers for its window. It
#: is not where the project's own facts are kept.
LIFECYCLE_VIEW_METHODS = [
    "translate",
    "show_status",
    "project_name",
    "sync_to_state",
    "connect_project",
    "apply_loaded_settings",
    "project_opened",
    "prepare_close",
    "prepare_model_replacement",
    "flush_pending_edits",
    "disconnect_project",
    "project_closed",
    "confirm_unsaved_changes",
    "show_save_failures",
    "show_load_failures",
    "capture_project_state",
]


class TestTheProjectFlushesItsOwnTextBuffers(unittest.TestCase):
    """The shared buffers are the project's, so the project flushes them.

    One document open in three windows is one buffer holding its text, but
    the flush ran per window and each window flushed all of the project's
    buffers -- the same work once per window. Worse, it was work only a
    window could ask for: a save while no window was registered wrote the
    models as they stood, with the pending text still sitting in buffers
    nothing had asked.
    """

    def setUp(self):
        self.storage = MagicMock()
        self.storage.save.return_value = ProjectSaveResult()
        self.buffers = MagicMock()

    def _manager(self, views):
        manager = ProjectManager(
            ProjectViewRegistry(views),
            MagicMock(),
            MagicMock(),
            storage=self.storage,
            model_factory=MagicMock(),
            autosave=MagicMock(),
            last_project_store=MagicMock(),
            revision_coordinator=MagicMock(),
            document_buffers=self.buffers,
        )
        manager.session.open("book.msk")
        return manager

    def test_two_windows_flush_the_shared_buffers_once_between_them(self):
        first, second = MagicMock(), MagicMock()

        self._manager([first, second]).saveDatas()

        self.buffers.flush.assert_called_once_with()
        # Each window is still asked for the text only it holds.
        first.flush_pending_edits.assert_called_once_with()
        second.flush_pending_edits.assert_called_once_with()

    def test_a_save_with_no_window_registered_still_writes_the_text(self):
        self._manager([]).saveDatas()

        self.buffers.flush.assert_called_once_with()

    def test_the_buffers_are_flushed_before_anything_is_written(self):
        order = []
        self.buffers.flush.side_effect = lambda: order.append("flush")
        self.storage.save.side_effect = (
            lambda _context: order.append("save") or ProjectSaveResult()
        )

        self._manager([MagicMock()]).saveDatas()

        self.assertEqual(order, ["flush", "save"])


class TestTheProjectIsNotReadThroughAWindow(unittest.TestCase):
    """The manager holds the project's things; the view only shows them.

    The settings, the parent the models hang off and the list of models
    whose edits mean unsaved changes all used to be read back out of the
    lifecycle view -- which owns none of them and merely pointed at the
    runtime that does. The manager could therefore not build models or
    save a project unless some window existed to be asked.

    The view here answers only the calls in LIFECYCLE_VIEW_METHODS;
    reaching for anything else raises, which is what lets these tests
    fail rather than quietly pass on a MagicMock that invents attributes.
    """

    def setUp(self):
        self.view = MagicMock(spec=LIFECYCLE_VIEW_METHODS)
        self.view.translate.side_effect = lambda text: text
        self.settings = MagicMock()
        self.model_parent = MagicMock()
        self.model_factory = MagicMock()
        self.storage = MagicMock()
        self.storage.save.return_value = ProjectSaveResult()
        self.revisions = MagicMock()
        self.manager = ProjectManager(
            self.view,
            self.settings,
            self.model_parent,
            storage=self.storage,
            model_factory=self.model_factory,
            autosave=MagicMock(),
            last_project_store=MagicMock(),
            revision_coordinator=self.revisions,
        )

    def test_models_are_built_from_the_projects_settings_and_parent(self):
        models = self.manager.loadEmptyDatas()

        self.model_factory.create.assert_called_once_with(
            self.model_parent,
            self.settings,
        )
        self.assertIs(models, self.model_factory.create.return_value)

    def test_a_save_finds_the_settings_without_asking_a_window(self):
        self.manager.session.open("book.msk")

        self.assertTrue(self.manager.saveDatas())

        context = self.storage.save.call_args[0][0]
        self.assertIs(context.settings, self.settings)
        self.revisions.after_project_save.assert_called_once_with(
            "book.msk",
            self.settings,
            message=None,
        )

    def test_settling_before_a_close_reads_the_projects_own_settings(self):
        """saveOnQuit is a project setting, so the project reads it."""
        self.manager.session.open("book.msk")
        self.settings.saveOnQuit = True

        self.assertTrue(self.manager.settleBeforeClosing())

        self.storage.save.assert_called_once()

    def test_what_marks_the_project_dirty_comes_from_its_own_models(self):
        first, second = MagicMock(), MagicMock()
        models = MagicMock()
        models.change_sources = (first, second)
        self.manager.models = models

        self.manager._connectModelChanges()

        for model in (first, second):
            model.dataChanged.connect.assert_called_once_with(
                self.manager.startTimerNoChanges,
            )

    def test_outline_reference_index_tracks_edits_and_structure(self):
        models = MagicMock()
        models.change_sources = ()
        self.manager.models = models

        self.manager._connectModelChanges()

        models.outline.dataChanged.connect.assert_called_once_with(
            self.manager._outlineReferencesChanged,
        )
        for signal in (
            models.outline.rowsInserted,
            models.outline.rowsRemoved,
            models.outline.modelReset,
        ):
            signal.connect.assert_called_once_with(
                self.manager._outlineReferenceStructureChanged,
            )

        index = MagicMock()
        index.isValid.return_value = True
        item = index.internalPointer.return_value
        self.manager._outlineReferencesChanged(index, index)
        self.manager._outlineReferenceStructureChanged()

        self.storage.update_document_references.assert_called_once_with(item)
        self.storage.rebuild_document_references.assert_called_once_with(
            models.outline.rootItem
        )

    def test_no_models_yet_means_nothing_to_watch_rather_than_a_crash(self):
        """A project opened from data already in memory never went through
        loadEmptyDatas, so there may be no model graph to connect.
        """
        self.manager.models = None

        self.manager._connectModelChanges()

        self.assertEqual(len(self.manager.modelConnections), 0)
