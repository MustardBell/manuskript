from dataclasses import dataclass
from copy import deepcopy

from manuskript.services.project_model_factory import ProjectModelFactory
from manuskript.services.project_persistence import (
    ProjectPersistenceContext,
)
from manuskript.services.project_storage import ProjectStorage
from manuskript.settingsManager import SettingsManager


class DetachedSettingsManager(SettingsManager):
    """Load project settings without changing application-wide Qt state."""

    def apply_loaded_settings_effects(self):
        pass


@dataclass(frozen=True)
class LoadedRevisionSnapshot:
    commit_id: str
    models: object
    settings: object
    load_result: object
    canonical_project: object = None


class RevisionSnapshotLoader:
    """Validate a Git snapshot in a model graph not bound to the UI."""

    def __init__(self, model_factory=None, storage=None):
        self.model_factory = model_factory or ProjectModelFactory()
        self.storage = storage or ProjectStorage()

    def load(self, project_file, snapshot, *, parent=None):
        settings = DetachedSettingsManager()
        models = self.model_factory.create(parent, settings)
        context = ProjectPersistenceContext(
            project_file=project_file,
            models=models,
            settings=settings,
        )
        result = self.storage.load_snapshot(context, snapshot)
        return LoadedRevisionSnapshot(
            commit_id=snapshot.commit_id,
            models=models,
            settings=settings,
            load_result=result,
            canonical_project=self.storage.canonical_project,
        )

    @staticmethod
    def preserve_revision_configuration(
        loaded_snapshot,
        current_settings,
    ):
        """Keep the active backend while restoring authored project data."""
        loaded_snapshot.settings.revisions = deepcopy(
            current_settings.revisions
        )
        return loaded_snapshot
