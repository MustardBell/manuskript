import os

from PyQt5.QtCore import QSettings, QTimer

from manuskript.domain.project import (
    CloseDecision,
    InvalidProjectStateTransition,
    ProjectSession,
)
from manuskript.logging import getLogFilePath
from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import (
    ProjectPersistenceContext,
)
from manuskript.services.project_storage import ProjectStorage
from manuskript.ui.connections import SignalConnectionRegistry

import logging
LOGGER = logging.getLogger(__name__)


class ProjectManager:
    def __init__(
            self, lifecycle_view, storage=None, status_reporter=None,
            model_factory=None):
        self.ui = lifecycle_view
        self.storage = storage if storage is not None else ProjectStorage()
        self.model_factory = model_factory or ProjectModelFactory()
        self.models = None
        self.status_reporter = status_reporter or (
            lambda message, duration=5000, importance=1: None
        )
        self.session = ProjectSession()
        self.modelConnections = SignalConnectionRegistry()
        self.saveTimer = QTimer()
        self.saveTimerNoChanges = QTimer()
        self.saveTimer.timeout.connect(self.saveDatas)
        self.saveTimerNoChanges.timeout.connect(self.saveDatas)

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
                self.saveTimer.stop()
                self.saveTimerNoChanges.stop()
                self.storage.clear_cache()
                return False

        self.session.open(project)
        self.ui.connect_project()
        self.ui.apply_loaded_settings()

        # Set autosave
        self.saveTimer.setInterval(
            self.ui.settings.autoSaveDelay * 60 * 1000
        )
        self.saveTimer.setSingleShot(False)
        if self.ui.settings.autoSave:
            self.saveTimer.start()

        # Set autosave if no changes
        self.saveTimerNoChanges.setInterval(
            self.ui.settings.autoSaveNoChangesDelay * 1000
        )
        self.saveTimerNoChanges.setSingleShot(True)
        for model in self.ui.change_models():
            self.modelConnections.connect(
                model.dataChanged, self.startTimerNoChanges
            )
        self.saveTimerNoChanges.stop()

        self.syncUiToState()
        QSettings().setValue("lastProject", project)
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
        if self.session.is_dirty and self.ui.settings.saveOnQuit:
            if not self.saveDatas():
                return False
        elif not self.handleUnsavedChanges():
            return False  # user cancelled action

        # Close open tabs in editor
        self.ui.prepare_close()

        self.session.close()
        QSettings().setValue("lastProject", "")

        self.saveTimer.stop()
        self.saveTimerNoChanges.stop()
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

        if self.ui.settings.autoSaveNoChanges:
            self.saveTimerNoChanges.start()
        return True

    def saveDatas(self, projectName=None):
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
        self.saveTimerNoChanges.stop()

        if not self.session.is_open:
            # No UI feedback here as this code path indicates a race condition that happens
            # after the user has already closed the project through some way. But in that
            # scenario, this code should not be reachable to begin with.
            LOGGER.error("There is no current project to save.")
            return False

        result = self.storage.save(
            self.persistence_context(self.currentProject)
        )
        if result.failed_files:
            self.ui.show_save_failures(result.failed_files)

        current_project_name = os.path.basename(self.currentProject)
        if result.succeeded:
            self.session.mark_clean()
            QSettings().setValue("lastProject", self.currentProject)

            feedback = self.ui.translate(
                "Project {} saved."
            ).format(current_project_name)
            self.status_reporter(feedback, importance=0)
            LOGGER.info("Project {} saved.".format(current_project_name))
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

    def loadEmptyDatas(self):
        self.models = self.model_factory.create(
            self.ui.model_parent,
            self.ui.settings,
        )
        self.ui.install_models(self.models)
        return self.models

    def loadDatas(self, project):
        result = self.storage.load(self.persistence_context(project))
        if result.unreadable_files:
            self.ui.show_load_failures(result.unreadable_files)
        errors = result.issues

        # Giving some feedback
        if not errors:
            LOGGER.info("Project {} loaded.".format(project))
            self.status_reporter(
                    self.ui.translate("Project {} loaded.").format(project), 2000)
        else:
            LOGGER.error("Project {} loaded with some errors:".format(project))
            for e in errors:
                LOGGER.error(" * {} wasn't found in project file.".format(e))
            self.status_reporter(
                    self.ui.translate("Project {} loaded with some errors.").format(project), 5000, importance = 3)
        
        if not result.succeeded:
            LOGGER.error("Loading project {} failed.".format(project))
            self.status_reporter(
                    self.ui.translate("Loading project {} failed.").format(project), 5000, importance = 3)

            return False
        
        return True

    def clearSaveCache(self):
        self.storage.clear_cache()

    def persistence_context(self, project_file):
        return ProjectPersistenceContext(
            project_file=project_file,
            models=self.models,
            settings=self.ui.settings,
        )
