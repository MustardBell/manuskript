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
    process_runner: object = None
    page_types: object = None
    #: What Markdown additionally means once it becomes HTML, as a callable
    #: answering with the augmentations that apply. A callable rather than a
    #: list because plugins come and go while an export dialog is open.
    html_augmentations: object = None

    @property
    def project_path(self):
        return os.path.dirname(os.path.abspath(self.project_file))
