#!/usr/bin/env python
# --!-- coding: utf8 --!--

# The loadSave file calls the proper functions to load and save file
# trying to detect the proper file format if it comes from an older version

import manuskript.load_save.version_0 as v0
import manuskript.load_save.version_1 as v1
from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.load_save.format_detection import (
    ProjectFormatDetector,
    ProjectFormatError,
    ProjectFormatRegistry,
)

import logging
LOGGER = logging.getLogger(__name__)
FORMAT_DETECTOR = ProjectFormatDetector()
FORMAT_REGISTRY = ProjectFormatRegistry(
    handlers={0: v0, 1: v1},
    current_version=1,
)


def saveProject(
    context,
    version=None,
    cache=None,
    file_access=None,
    legacy_file_access=None,
):
    # While debugging, we don't save the project
    # return

    try:
        selected_version, handler = FORMAT_REGISTRY.resolve(version)
    except ProjectFormatError as error:
        LOGGER.error("%s", error)
        return ProjectSaveResult(
            failed_files=(context.project_file,)
        )

    if selected_version == 0:
        return handler.saveProject(
            context,
            archive=legacy_file_access,
        )
    return handler.saveProject(
        context,
        cache=cache,
        file_access=file_access,
    )


def loadProject(
    context,
    cache=None,
    file_access=None,
    legacy_file_access=None,
):
    project = context.project_file
    try:
        detected = FORMAT_DETECTOR.detect(project)
        version, handler = FORMAT_REGISTRY.resolve(
            detected.version
        )
    except ProjectFormatError as error:
        LOGGER.error("%s", error)
        return ProjectLoadResult(
            fatal_errors=(str(error),)
        )

    LOGGER.info("Loading: %s", project)
    LOGGER.info(
        "Detected file format version: %s. Zip: %s.",
        version,
        detected.zipped,
    )

    if version == 0:
        return handler.loadProject(
            context,
            archive=legacy_file_access,
        )
    return handler.loadProject(
        context,
        zip=detected.zipped,
        cache=cache,
        file_access=file_access,
    )
