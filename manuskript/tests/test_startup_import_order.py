"""Importing the entry point must not freeze the palette.

``manuskript.ui.style`` reads ``qApp.palette()`` at module scope and derives
every interface colour from it, once, for the life of the process. So whatever
imports it first decides what the whole application looks like.

``manuskript.main`` is imported before a QApplication exists at all. If
anything it imports at module scope reaches ``ui.style``, the snapshot is
taken from Qt's built-in default palette -- navy highlight, grey window --
instead of the style Manuskript goes on to choose, and selections turn purple
everywhere.

This happened. The vector was innocuous: a migration module importing
``manuskript.exporter.page_routes`` for two names, which executes the whole
exporter package, which reaches exporter settings widgets, which import
``ui.style``. Nothing in the code looked wrong at any step.
"""

import subprocess
import sys


#: Modules that must not be reachable at ``manuskript.main`` import time,
#: with why. Add to this rather than relaxing the test.
FORBIDDEN = {
    "manuskript.ui.style":
        "snapshots qApp.palette() at import, before a style is chosen",
}


def imported_by(module):
    """Every manuskript module a fresh interpreter loads for ``module``.

    Run out of process: this cannot be measured in a test session where
    other tests have already imported half the application.
    """
    program = (
        "import sys\n"
        "import {}\n"
        "print('\\n'.join(sorted(\n"
        "    name for name in sys.modules if name.startswith('manuskript')\n"
        ")))\n"
    ).format(module)
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return set(result.stdout.split())


def test_the_entry_point_does_not_reach_the_palette_snapshot():
    loaded = imported_by("manuskript.main")

    offenders = {
        name: reason
        for name, reason in FORBIDDEN.items()
        if name in loaded
    }

    assert not offenders, (
        "Importing manuskript.main pulled in {}. Move the import that "
        "reaches it inside a function: every colour in the interface is "
        "derived from a palette read at import time, so an early import "
        "makes the whole application the wrong colour and nothing "
        "fails.".format(offenders)
    )


def test_the_preferences_migration_stays_clear_of_the_exporter_package():
    # The specific regression: two names were worth importing lazily, and
    # the exporter package reaches Qt widgets on the way to providing them.
    loaded = imported_by("manuskript.preferences_migrations")

    assert "manuskript.ui.style" not in loaded
    assert not any(
        name.startswith("manuskript.exporter") for name in loaded
    ), sorted(name for name in loaded if name.startswith("manuskript."))


#: Modules that must import on their own, as the first manuskript module a
#: process loads. Add to this rather than relying on something else being
#: imported first.
STANDS_ALONE = (
    "manuskript.converters.conversion_service",
    "manuskript.models.reference_identity",
    "manuskript.models.references",
    "manuskript.plugins",
    "manuskript.plugins.runtime",
    "manuskript.plugins.capabilities",
    "manuskript.media_types",
    "manuskript.preferences_migrations",
    "manuskript.services.reference_service",
)


def imports_alone(module):
    """Whether a fresh interpreter can import ``module`` and nothing else
    first, or the error it gives instead."""
    result = subprocess.run(
        [sys.executable, "-c", "import {}".format(module)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stderr


def test_no_module_needs_another_one_imported_before_it():
    """A cycle between two modules is invisible while something else always
    imports one of them first -- a test session, or the entry point -- and
    then fails for whoever imports the other one directly. Two of these
    reached each other: the conversion service reads the plugin API, and the
    plugin runtime builds a conversion service.
    """
    failures = {}
    for module in STANDS_ALONE:
        ok, error = imports_alone(module)
        if not ok:
            failures[module] = error.strip().splitlines()[-1:]

    assert not failures, failures


def test_the_guard_would_notice_the_regression():
    # Proof the measurement works: this module really does reach ui.style,
    # so a passing result above is a fact about main rather than a fact
    # about the check being unable to see anything.
    loaded = imported_by("manuskript.exporter.page_routes")

    assert "manuskript.ui.style" in loaded
