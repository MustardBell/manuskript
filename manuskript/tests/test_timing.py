"""Milestones say how long a blocking step took, when asked and not before.

Two properties matter more than the numbers. It has to be free when nobody
asked -- instrumentation that costs something is instrumentation somebody
removes -- and it has to report a step that ended badly, since a step that
failed after two seconds is exactly what a person measuring wants to see.
"""

import io
import logging

import pytest

from manuskript import timing
from manuskript.main import process_commandline


@pytest.fixture
def measured():
    """Capture milestones, and leave the logger as it was found."""
    stream = io.StringIO()
    handler = timing.enable(stream)
    try:
        yield stream
    finally:
        timing.LOGGER.removeHandler(handler)
        timing.LOGGER.setLevel(logging.NOTSET)
        timing.LOGGER.propagate = True


def test_nothing_is_measured_unless_asked():
    """The default, and the reason every call site can be unconditional."""
    assert not timing.measuring()

    timing.mark("nobody.asked")
    with timing.span("nobody.asked.either"):
        pass


def test_a_span_reports_what_it_took():
    stream = io.StringIO()
    handler = timing.enable(stream)
    try:
        with timing.span("project.open"):
            pass
    finally:
        timing.LOGGER.removeHandler(handler)
        timing.LOGGER.setLevel(logging.NOTSET)
        timing.LOGGER.propagate = True

    reported = stream.getvalue()
    assert "project.open" in reported
    assert "took" in reported
    assert "ms" in reported


def indent_of(line):
    """How deep a milestone is nested.

    The number is a fixed-width field, so where " ms" falls in the line
    differs by exactly the indent in front of it.
    """
    return line.index(" ms")


def milestone(reported, name):
    return next(
        line for line in reported.splitlines()
        if line.endswith(name) or "  {}  ".format(name) in line
    )


def test_a_span_inside_a_span_is_shown_under_it(measured):
    """Which is the point of measuring: a load taking 400 ms means nothing
    until you can see which 300 of them were the files.
    """
    with timing.span("project.open"):
        with timing.span("project.open.read"):
            pass

    reported = measured.getvalue()
    inner = milestone(reported, "project.open.read")
    outer = milestone(reported, "project.open")

    assert indent_of(inner) > indent_of(outer)
    # The inner one finishes first, so it is reported first.
    lines = reported.splitlines()
    assert lines.index(inner) < lines.index(outer)


def test_a_step_that_failed_is_still_reported(measured):
    with pytest.raises(ValueError):
        with timing.span("project.open"):
            raise ValueError("no project today")

    reported = measured.getvalue()
    assert "project.open" in reported
    assert "failed: ValueError" in reported


def test_depth_recovers_from_a_failure(measured):
    """Otherwise one failed step indents everything after it forever."""
    with pytest.raises(ValueError):
        with timing.span("outer"):
            raise ValueError("stop")

    with timing.span("later"):
        pass

    reported = measured.getvalue()

    assert indent_of(milestone(reported, "later")) == indent_of(
        milestone(reported, "outer")
    )


def test_a_mark_says_how_far_into_the_session_it_happened(measured):
    timing.mark("startup.prepared")

    reported = measured.getvalue()
    assert "startup.prepared" in reported
    assert timing.since_start() > 0


def test_milestones_do_not_land_in_the_ordinary_log(measured, caplog):
    """They answer a question somebody asked at the command line; the log
    file is for everything else.
    """
    with caplog.at_level(logging.DEBUG):
        timing.mark("startup.prepared")

    assert "startup.prepared" not in caplog.text


def test_measuring_is_off_unless_the_flag_is_given():
    assert process_commandline([]).measure_time is False
    assert process_commandline(["--measure-time"]).measure_time is True
