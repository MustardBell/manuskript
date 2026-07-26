from dataclasses import dataclass

from manuskript.services.project_model_factory import ProjectModels


@dataclass(frozen=True)
class ProjectPersistenceContext:
    """All state required to serialize or hydrate one project."""

    project_file: str
    models: ProjectModels
    settings: object
