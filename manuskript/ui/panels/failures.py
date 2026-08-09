"""Saying that a panel could not be opened, without blocking on it.

This was a modal dialog once. A modal turns any factory fault into
something that waits for a person, which in a test run is a hang rather
than a failure -- the suite stopped at the same point twice before I
believed it.

Told, not asked: the status bar carries it where there is one, and the log
always does, so a broken panel costs the person a line rather than their
attention. Where to say it is the only real question, and it has two
answers in a preference order: whoever asked for the panel supplied a way
to report, or the window has a status bar of its own.
"""

import logging


LOGGER = logging.getLogger(__name__)

#: Long enough to read, since nothing repeats it.
DURATION = 8000

#: Warning rather than error: the application is fine, one panel is not.
IMPORTANCE = 2


class PanelFailureReporter:
    """Where one window says a panel could not be built."""

    def __init__(self, translate, fallback_reporter=None):
        self._translate = translate
        self._fallback_reporter = fallback_reporter

    def report(self, descriptor, error, context=None):
        message = self._translate(
            "The {} panel could not be opened: {}"
        ).format(descriptor.title, error)
        LOGGER.warning(
            "Panel %s failed to build: %s", descriptor.id, error,
        )
        show_status = self._reporter(context)
        if show_status is not None:
            show_status(message, DURATION, IMPORTANCE)
        return message

    def _reporter(self, context):
        """Whoever can put a line in front of the person, or nobody.

        Nobody is a legal answer: a panel opened into a window that has no
        status bar still must not be able to stop anything.
        """
        show_status = getattr(context, "show_status", None)
        if show_status is not None:
            return show_status
        return self._fallback_reporter
