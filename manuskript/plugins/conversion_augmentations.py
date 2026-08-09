"""Building what plugins add to a conversion, for one rendering.

The contributions say what they are; this makes the objects the engine for
that route accepts. Kept apart from both, so the registry stays a catalogue
and the converter stays a converter, and so a plugin whose addition will not
build costs the reader a rendering without it rather than no rendering.

Nothing here names a format. The route arrives as a request from whoever is
performing the conversion, which is the only code entitled to say what it is
converting.
"""

import logging

from manuskript.plugins.applicable import applicable


LOGGER = logging.getLogger(__name__)


def augmentations_for(registry, request, report_error=None):
    """What plugins add to this conversion, in the order they apply.

    Highest priority first, because an addition may have to see the source
    before another one can say so.

    An addition that will not build is reported and skipped. A plugin's fault
    must not be the difference between a rendering happening and not.
    """
    if registry is None or request is None:
        return []
    try:
        contributions = applicable(
            registry.conversion_augmentations, request,
        )
    except Exception:
        LOGGER.exception(
            "Cannot read the registered conversion augmentations."
        )
        return []

    built = []
    for contribution in contributions:
        try:
            addition = contribution.augmentation_factory()
        except Exception as error:
            LOGGER.warning(
                "Conversion augmentation %s could not be built: %s",
                contribution.descriptor.id,
                error,
            )
            if report_error is not None:
                report_error(
                    "The {} addition could not be used: {}".format(
                        contribution.descriptor.name, error
                    )
                )
            continue
        if addition is not None:
            built.append(addition)
    return built
