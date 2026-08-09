import os
from dataclasses import dataclass
from typing import Callable


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
    #: What plugins add to a conversion, as a callable taking a
    #: ConversionRequest and answering with the additions that apply. A
    #: callable rather than a list because plugins come and go while an
    #: export dialog is open, and because only the code performing a
    #: conversion knows which one it is performing.
    conversion_augmentations: object = None

    @property
    def project_path(self):
        return os.path.dirname(os.path.abspath(self.project_file))


@dataclass(frozen=True)
class ExportContextProvider:
    """Build a fresh export context from live project capabilities.

    Models and plugin routes can change while a workspace remains open, so
    they are resolved for each request instead of being captured in a dialog
    or copied onto ``MainWindow``.
    """

    project_file: Callable[[], str]
    models: Callable[[], object]
    parent: object
    tool_paths: object = None
    process_runner: object = None
    page_types: Callable[[], object] = None
    conversion_augmentations: object = None

    def create(self):
        models = self.models()
        return ExportContext(
            project_file=self.project_file() or "",
            outline_model=models.outline,
            flat_data_model=models.flat_data,
            label_model=models.labels,
            status_model=models.statuses,
            parent=self.parent,
            tool_paths=self.tool_paths,
            process_runner=self.process_runner,
            page_types=(
                self.page_types()
                if self.page_types is not None
                else None
            ),
            conversion_augmentations=self.conversion_augmentations,
        )
