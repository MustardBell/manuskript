import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ExportContext:
    """Project data and UI ownership required by an export operation."""

    project_file: str
    outline_model: object
    flat_data_model: object
    label_model: object
    status_model: object
    parent: object
    tool_paths: object = None

    @property
    def project_path(self):
        return os.path.dirname(os.path.abspath(self.project_file))
