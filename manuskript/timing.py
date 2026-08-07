"""Where the time goes, when somebody asks and not otherwise.

Off by default and free when off. ``--measure-time`` turns it on for one
run, and every milestone becomes a line on stderr saying how long the
blocking step took and how far into the session it happened.

A sibling of :mod:`manuskript.logging` rather than an injected collaborator,
and deliberately so. Timing has to be reachable from the middle of a
constructor, a load path and a save path without any of them being handed a
recorder -- and it is a diagnostic, not behaviour: nothing downstream reads
it, nothing changes because of it. That is the same argument logging makes,
so this uses logging rather than inventing a second version of it.

Nesting is tracked, so a span inside a span is indented under it. That is
the whole point of measuring: ``project.load`` taking 400 ms only means
something once you can see which 300 of them were the files.
"""

import logging
import time

from contextlib import contextmanager


LOGGER = logging.getLogger("manuskript.timing")

#: When this module was imported, which is as close to "when the process
#: started" as Python can portably get. main imports it first.
ORIGIN = time.perf_counter()

_depth = 0


def enable(stream=None, level=logging.INFO):
    """Send milestones to stderr, or wherever ``stream`` says.

    Called once, from the entry point, when the flag is given. Everything
    below asks the logger whether it is worth measuring, so enabling is the
    only switch there is.
    """
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level)
    # Milestones are for whoever asked, not for the log file every other
    # message goes to.
    LOGGER.propagate = False
    mark("measuring")
    return handler


def measuring():
    """Whether anything is listening. Cheap: logging caches this."""
    return LOGGER.isEnabledFor(logging.INFO)


def since_start():
    """Seconds from process start to now."""
    return time.perf_counter() - ORIGIN


def mark(name):
    """Note that a moment happened, without timing anything around it."""
    if not measuring():
        return
    LOGGER.info(
        "[timing] %s%9.1f ms  %s",
        "  " * _depth,
        since_start() * 1000,
        name,
    )


@contextmanager
def span(name):
    """Time a blocking step, and say so when it ends.

    Reported when it ends rather than when it starts, because the number
    only exists then -- and reported even when it ends badly, since a step
    that failed after two seconds is exactly what somebody measuring wants
    to know.
    """
    global _depth
    if not measuring():
        yield
        return
    started = time.perf_counter()
    depth = _depth
    _depth += 1
    outcome = ""
    try:
        yield
    except BaseException as error:
        outcome = "  (failed: {})".format(type(error).__name__)
        raise
    finally:
        _depth = depth
        LOGGER.info(
            "[timing] %s%9.1f ms  %s  took %.1f ms%s",
            "  " * depth,
            since_start() * 1000,
            name,
            (time.perf_counter() - started) * 1000,
            outcome,
        )
