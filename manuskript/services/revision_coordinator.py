import datetime
import logging

from manuskript.domain.revisions import RevisionConfiguration
from manuskript.services.git_revisions import GitRevisionBackend
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

    def load_snapshot(self, project_file, revision, settings, parent=None):
        """One revision as a validated, separate model.

        The coordinator knows Git and snapshots; what happens to the
        loaded model is the project manager's business, so this takes
        plain data and never a project manager.
        """
        git_snapshot = self.git_backend(project_file).snapshot(revision)
        loaded = self.snapshot_loader.load(
            project_file,
            git_snapshot,
            parent=parent,
        )
        self.snapshot_loader.preserve_revision_configuration(
            loaded,
            settings,
        )
        return loaded

    def create_tag(self, project_file, revision, name):
        return self.git_backend(project_file).create_tag(
            revision,
            name,
        )
