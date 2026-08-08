"""Building what plugins add to Markdown, for one rendering.

The contributions say what they are; this makes the objects the converter
takes. Kept apart from both so that the registry stays a catalogue and the
converter stays a converter, and so that a plugin whose extension will not
build costs the reader a rendering without its addition rather than no
rendering at all.
"""

import logging

from manuskript.plugins.applicable import applicable


LOGGER = logging.getLogger(__name__)


def markdown_extensions(registry, page_type=None, report_error=None):
    """The markdown extensions that apply to this rendering, in order.

    Highest priority first, because an addition that must see the source
    before another one can say so.

    An extension that will not build is reported and skipped. A plugin's
    fault must not be the difference between an export happening and not.
    """
    if registry is None:
        return []
    try:
        contributions = applicable(registry.html_augmentations, page_type)
    except Exception:
        LOGGER.exception("Cannot read the registered HTML augmentations.")
        return []

    built = []
    for contribution in contributions:
        try:
            extension = contribution.extension_factory()
        except Exception as error:
            LOGGER.warning(
                "HTML augmentation %s could not be built: %s",
                contribution.descriptor.id,
                error,
            )
            if report_error is not None:
                report_error(
                    "The {} addition to Markdown could not be used: "
                    "{}".format(contribution.descriptor.name, error)
                )
            continue
        if extension is not None:
            built.append(extension)
    return built
