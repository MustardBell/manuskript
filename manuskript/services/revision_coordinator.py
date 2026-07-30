import datetime
import logging

from manuskript.domain.revisions import RevisionConfiguration
from manuskript.services.git_revisions import (
    GitRevisionBackend,
    GitRevisionError,
)
from manuskript.services.revision_snapshot import RevisionSnapshotLoader


LOGGER = logging.getLogger(__name__)


class ProjectRevisionCoordinator:
    """Coordinate project lifecycle operations with revision backends."""

    def __init__(
        self,
        backend_factory=None,
        snapshot_loader=None,
    ):
        self.backend_factory = (
            backend_factory or GitRevisionBackend
        )
        self.snapshot_loader = (
            snapshot_loader or RevisionSnapshotLoader()
        )

    def git_backend(self, project_file):
        return self.backend_factory(project_file)

    def after_project_save(
        self,
        project_file,
        settings,
        *,
        message=None,
    ):
        configuration = RevisionConfiguration.from_mapping(
            settings.revisions
        )
        if not (
            configuration.uses_git
            and configuration.auto_commit
        ):
            return None
        if message is None:
            message = "Manuskript save {}".format(
                datetime.datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )
            )
        return self.git_backend(project_file).commit(message)

    def restore(self, project_manager, revision):
        backend = self.git_backend(
            project_manager.currentProject
        )
        git_snapshot = backend.snapshot(revision)
        loaded = self.snapshot_loader.load(
            project_manager.currentProject,
            git_snapshot,
            parent=project_manager.ui.model_parent,
        )
        self.snapshot_loader.preserve_revision_configuration(
            loaded,
            project_manager.ui.settings,
        )
        return project_manager.restoreRevisionSnapshot(loaded)

    def manual_commit(self, project_manager, message):
        project_manager.ui.flush_pending_edits()
        if not project_manager.saveDatas(record_revision=False):
            raise GitRevisionError(
                "The project could not be saved before committing."
            )
        return self.git_backend(
            project_manager.currentProject
        ).commit(message)

    def create_tag(self, project_file, revision, name):
        return self.git_backend(project_file).create_tag(
            revision,
            name,
        )
