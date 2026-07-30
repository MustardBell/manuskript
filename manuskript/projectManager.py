import os

from manuskript.domain.project import (
    CloseDecision,
    InvalidProjectStateTransition,
    ProjectSession,
)
from manuskript.logging import getLogFilePath
from manuskript.services.project_autosave import (
    ProjectAutosaveScheduler,
)
from manuskript.services.project_history import ProjectHistory
from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import (
    ProjectPersistenceContext,
)
from manuskript.services.project_storage import ProjectStorage
from manuskript.services.revision_coordinator import (
    ProjectRevisionCoordinator,
)
from manuskript.ui.connections import SignalConnectionRegistry

import logging
LOGGER = logging.getLogger(__name__)


class ProjectManager:
    def __init__(
            self, lifecycle_view, storage=None, status_reporter=None,
            model_factory=None, autosave=None, last_project_store=None,
            revision_coordinator=None):
        self.ui = lifecycle_view
        self.storage = storage if storage is not None else ProjectStorage()
        self.model_factory = model_factory or ProjectModelFactory()
        self.models = None
        self.status_reporter = status_reporter or (
            lambda message, duration=5000, importance=1: None
        )
        self.session = ProjectSession()
        self.modelConnections = SignalConnectionRegistry()
        self.autosave = autosave or ProjectAutosaveScheduler(
            self.saveDatas
        )
        self.last_project_store = (
            last_project_store or ProjectHistory()
        )
        self.revision_coordinator = (
            revision_coordinator or ProjectRevisionCoordinator()
        )

    @property
    def currentProject(self):
        return self.session.path

    @property
    def projectDirty(self):
        if not self.session.is_open:
            return None
        return self.session.is_dirty

    def syncUiToState(self):
        """Enable project actions according to the current session state."""
        self.ui.sync_to_state(self.session.is_open)

    def loadProject(self, project, loadFromFile=True):
        """Loads the project ``project``.

        If ``loadFromFile`` is False, then it does not load datas from file.
        It assumes that the datas have been populated in a different way."""

        # Convert project path to OS norm
        project = os.path.normpath(project)

        if loadFromFile and not os.path.exists(project):
            LOGGER.warning("The file {} does not exist. Has it been moved or deleted?".format(project))
            self.status_reporter(
                    self.ui.translate("The file {} does not exist. Has it been moved or deleted?").format(project), importance=3)
            return False

        if self.session.is_open:
            LOGGER.error(
                "Cannot load project %s while project %s is still open.",
                project,
                self.currentProject,
            )
            return False

        if loadFromFile:
            # Reset settings to defaults
            self.ui.settings.reset_to_defaults()

            # Load data
            self.loadEmptyDatas()
            
            if not self.loadDatas(project):
                self.autosave.stop()
                self.storage.clear_cache()
                return False

        self.session.open(project)
        self.ui.connect_project()
        self.ui.apply_loaded_settings()

        self.reconfigureAutosave()
        self._connectModelChanges()

        self.syncUiToState()
        self.last_project_store.remember_last_project(project)
        self.ui.project_opened()
        return True

    def handleUnsavedChanges(self):
        """
        There may be some currently unsaved changes, but the action the user triggered
        will result in the project or application being closed. To save, or not to save?

        Or just bail out entirely?

        Sometimes it is best to just ask.
        """

        if not self.session.is_dirty:
            return True  # no unsaved changes, all is good

        decision = self.ui.confirm_unsaved_changes()
        if decision is CloseDecision.CANCEL:
            return False
        if decision is CloseDecision.SAVE:
            return self.saveDatas()
        return True


    def closeProject(self):

        if not self.session.is_open:
            return True

        # Make sure data is saved.
        if self.ui.settings.saveOnQuit:
            if not self.saveDatas():
                return False
        elif not self.handleUnsavedChanges():
            return False  # user cancelled action

        # Close open tabs in editor
        self.ui.prepare_close()

        self.session.close()
        self.last_project_store.clear_last_project()

        self.autosave.stop()
        self.modelConnections.disconnect_all()
        self.ui.disconnect_project()

        # Clear datas
        self.loadEmptyDatas()
        self.storage.clear_cache()

        self.syncUiToState()

        self.ui.project_closed()
        return True

    def startTimerNoChanges(self):
        """
        Something changed in the project that requires auto-saving.
        """
        try:
            self.session.mark_dirty()
        except InvalidProjectStateTransition:
            LOGGER.warning("Ignoring a project change after the project was closed.")
            return False

        self.autosave.schedule_after_change()
        return True

    def saveDatas(
        self,
        projectName=None,
        *,
        revision_message=None,
        record_revision=True,
    ):
        """Saves the current project (in self.currentProject).

        If ``projectName`` is given, currentProject becomes projectName.
        In other words, it "saves as...".
        """

        previous_project = self.currentProject
        if projectName:
            try:
                self.session.rename(projectName)
            except InvalidProjectStateTransition:
                LOGGER.error("There is no current project to save as %s.", projectName)
                return False

        # Stop the timer before saving: if auto-saving fails (bugs out?) we don't want it
        # to keep trying and continuously hitting the failure condition. Nor do we want to
        # risk a scenario where the timer somehow triggers a new save while saving.
        self.autosave.saving_started()

        if not self.session.is_open:
            # No UI feedback here as this code path indicates a race condition that happens
            # after the user has already closed the project through some way. But in that
            # scenario, this code should not be reachable to begin with.
            LOGGER.error("There is no current project to save.")
            return False

        self.ui.capture_project_state()
        result = self.storage.save(
            self.persistence_context(self.currentProject)
        )
        if result.failed_files:
            self.ui.show_save_failures(result.failed_files)

        current_project_name = os.path.basename(self.currentProject)
        if result.succeeded:
            self.session.mark_clean()
            self.last_project_store.remember_last_project(
                self.currentProject
            )

            feedback = self.ui.translate(
                "Project {} saved."
            ).format(current_project_name)
            self.status_reporter(feedback, importance=0)
            LOGGER.info("Project {} saved.".format(current_project_name))
            if record_revision:
                self._recordRevisionAfterSave(revision_message)
        else:
            if projectName:
                self.session.rename(previous_project)
            feedback = self.ui.translate(
                "WARNING: Project {} not saved."
            ).format(
                current_project_name
            )
            self.status_reporter(feedback, importance=3)
            LOGGER.warning("Project {} not saved.".format(current_project_name))
        return result.succeeded

    def _recordRevisionAfterSave(self, message):
        try:
            self.revision_coordinator.after_project_save(
                self.currentProject,
                self.ui.settings,
                message=message,
            )
        except Exception as error:
            LOGGER.exception(
                "Project saved, but its Git revision could not be "
                "recorded."
            )
            self.status_reporter(
                self.ui.translate(
                    "Project saved, but Git could not record the "
                    "revision: {}"
                ).format(str(error)),
                importance=2,
            )

    def loadEmptyDatas(self):
        self.models = self.model_factory.create(
            self.ui.model_parent,
            self.ui.settings,
        )
        self.ui.install_models(self.models)
        return self.models

    def restoreRevisionSnapshot(self, snapshot):
        """Replace the project through validated models, never Git checkout."""
        if not self.session.is_open:
            LOGGER.error(
                "Cannot restore a revision when no project is open."
            )
            return False
        if not snapshot.load_result.succeeded:
            LOGGER.error(
                "Cannot restore invalid revision snapshot %s.",
                snapshot.commit_id,
            )
            return False

        self.ui.flush_pending_edits()
        if not self.saveDatas(
            revision_message="Before restoring revision {}".format(
                snapshot.commit_id[:10]
            )
        ):
            LOGGER.error(
                "Cannot preserve the current project before restoring %s.",
                snapshot.commit_id,
            )
            return False

        previous_models = self.models
        previous_settings = self.ui.settings.save()
        restored_settings = snapshot.settings.save()
        replacement_attempted = False

        self.autosave.stop()
        self.ui.prepare_model_replacement()
        self._disconnectModelChanges()
        self.ui.disconnect_project()

        try:
            replacement_attempted = True
            self._installProjectState(
                snapshot.models,
                restored_settings,
            )
            self.session.mark_dirty()
            if not self.saveDatas(
                revision_message="Restore revision {}".format(
                    snapshot.commit_id[:10]
                )
            ):
                raise RuntimeError(
                    "The restored revision could not be saved."
                )
        except Exception:
            LOGGER.exception(
                "Restoring revision %s failed; reinstating the "
                "previous project state.",
                snapshot.commit_id,
            )
            rollback_succeeded = self._rollbackProjectState(
                previous_models,
                previous_settings,
                replacement_attempted,
            )
            self.reconfigureAutosave()
            if not rollback_succeeded:
                self.status_reporter(
                    self.ui.translate(
                        "Revision restore failed, and the previous "
                        "project could not be written back completely."
                    ),
                    importance=3,
                )
            else:
                self.status_reporter(
                    self.ui.translate(
                        "Revision restore failed; the previous "
                        "project was restored."
                    ),
                    importance=3,
                )
            return False

        self._disposeModels(previous_models)
        self.reconfigureAutosave()
        self.ui.project_opened()
        self.status_reporter(
            self.ui.translate(
                "Revision {} restored."
            ).format(snapshot.commit_id[:10]),
            importance=0,
        )
        return True

    def _installProjectState(self, models, serialized_settings):
        self.ui.settings.load(
            serialized_settings,
            fromString=True,
            protocol=0,
        )
        self._adoptLiveSettings(models)
        self.models = models
        self.ui.install_models(models)
        self.ui.connect_project()
        self.ui.apply_loaded_settings()
        self._connectModelChanges()

    def _rollbackProjectState(
        self,
        previous_models,
        previous_settings,
        replacement_attempted,
    ):
        self._disconnectModelChanges()
        if replacement_attempted:
            try:
                self.ui.disconnect_project()
            except Exception:
                LOGGER.exception(
                    "Cannot release the failed revision model bindings."
                )

        try:
            self._installProjectState(
                previous_models,
                previous_settings,
            )
            self.session.mark_dirty()
            rollback_succeeded = self.saveDatas(
                record_revision=False
            )
            self.ui.project_opened()
            return rollback_succeeded
        except Exception:
            LOGGER.exception(
                "Cannot reinstall the project state from before "
                "revision restore."
            )
            return False

    def _adoptLiveSettings(self, models):
        outline = getattr(models, "outline", None)
        if outline is None:
            return
        outline.settings = self.ui.settings
        outline.rootItem.setModel(outline)

    def _connectModelChanges(self):
        for model in self.ui.change_models():
            self.modelConnections.connect(
                model.dataChanged,
                self.startTimerNoChanges,
            )

    def _disconnectModelChanges(self):
        self.modelConnections.disconnect_all()

    @staticmethod
    def _disposeModels(models):
        if models is None:
            return
        for model in vars(models).values():
            delete_later = getattr(model, "deleteLater", None)
            if delete_later is not None:
                delete_later()

    def loadDatas(self, project):
        result = self.storage.load(self.persistence_context(project))
        if result.unreadable_files:
            self.ui.show_load_failures(result.unreadable_files)

        if not result.succeeded:
            LOGGER.error("Loading project %s failed:", project)
            for error in result.fatal_errors:
                LOGGER.error(" * %s", error)
            self.status_reporter(
                self.ui.translate(
                    "Loading project {} failed."
                ).format(project),
                5000,
                importance=3,
            )
            return False

        if result.issues:
            LOGGER.warning(
                "Project %s loaded with recoverable errors:",
                project,
            )
            for filename in result.missing_files:
                LOGGER.warning(" * Missing file: %s", filename)
            for filename in result.unreadable_files:
                LOGGER.warning(" * Unreadable file: %s", filename)
            self.status_reporter(
                self.ui.translate(
                    "Project {} loaded with some errors."
                ).format(project),
                5000,
                importance=3,
            )
        else:
            LOGGER.info("Project %s loaded.", project)
            self.status_reporter(
                self.ui.translate(
                    "Project {} loaded."
                ).format(project),
                2000,
            )
        return True

    def clearSaveCache(self):
        self.storage.clear_cache()

    def reconfigureAutosave(self):
        settings = self.ui.settings
        self.autosave.configure(
            periodic_enabled=settings.autoSave,
            periodic_delay_minutes=settings.autoSaveDelay,
            after_change_enabled=settings.autoSaveNoChanges,
            after_change_delay_seconds=(
                settings.autoSaveNoChangesDelay
            ),
        )

    def persistence_context(self, project_file):
        return ProjectPersistenceContext(
            project_file=project_file,
            models=self.models,
            settings=self.ui.settings,
        )
